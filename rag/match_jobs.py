"""
Main job matching pipeline using RAG (pgvector + Llama-3).
"""
import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client
from rag.embedding_service import get_embedding_service
from agents.groq_client import GroqClient
from utils.job_location import assess_sponsorship_language, assess_us_job_location


def get_resume_profiles(profile_name: Optional[str] = None) -> List[Dict]:
    """Get one named resume profile or all active profiles."""
    client = get_supabase_client()

    try:
        query = client.client.table("user_resume").select("*")
        if profile_name:
            query = query.ilike("profile_name", profile_name)
        else:
            query = query.eq("is_active", True)
        result = query.order("profile_name").execute()
        if result.data:
            return result.data
        print("No matching resume profiles found. Please upload a resume first.")
        return []
    except Exception as e:
        print(f"Error fetching resume profiles: {e}")
        return []


def find_similar_jobs(
    resume_embedding: List[float],
    limit: int = 50,
    threshold: float = 0.4,
) -> List[Dict]:
    """Find similar jobs using vector similarity search."""
    client = get_supabase_client()

    try:
        top_jobs = client.search_similar_jobs(
            resume_embedding,
            limit=limit,
            threshold=threshold,
        )
        if not top_jobs:
            print("No job embeddings found above the similarity threshold")
            return []

        job_ids = [j["job_id"] for j in top_jobs]
        # Read the JD first. Work-authorization eligibility must not depend on
        # whether this employer already appears in historical DOL filings.
        jobs_result = client.client.table("jobs").select("*").in_(
            "id", job_ids
        ).eq("is_active", True).execute()

        jobs_by_id = {job["id"]: job for job in jobs_result.data}
        jobs_with_scores = []
        excluded_locations = []
        excluded_authorization = []
        for match in top_jobs:
            job = jobs_by_id.get(match["job_id"])
            if job:
                eligible, reason = assess_us_job_location(
                    job.get("location", ""),
                    job.get("description", ""),
                )
                if not eligible:
                    excluded_locations.append(
                        f"{job.get('title', 'Untitled')} ({job.get('location', 'unknown')})"
                    )
                    continue
                authorization_eligible, authorization_reason = (
                    assess_sponsorship_language(
                        job.get("description", ""), job.get("title", "")
                    )
                )
                if not authorization_eligible:
                    excluded_authorization.append(
                        f"{job.get('title', 'Untitled')} ({authorization_reason})"
                    )
                    continue
                job["cosine_similarity"] = float(match["similarity"])
                jobs_with_scores.append(job)
        if excluded_locations:
            print(
                f"Location filter excluded {len(excluded_locations)} non-US-only "
                f"candidate(s): {'; '.join(excluded_locations)}"
            )

        if excluded_authorization:
            print(
                f"JD authorization filter excluded {len(excluded_authorization)} "
                f"candidate(s): {'; '.join(excluded_authorization)}"
            )

        # Only after the JD passes location and work-authorization checks do we
        # attach DOL history. Missing history remains an allowed, explicit state.
        company_ids = list(
            {
                job["company_id"]
                for job in jobs_with_scores
                if job.get("company_id") is not None
            }
        )
        companies_by_id = {}
        if company_ids:
            companies_result = client.client.table("companies").select(
                "id,employer_name,approval_rate,total_approvals,h1b_approvals,"
                "perm_approvals,lca_approvals"
            ).in_("id", company_ids).execute()
            companies_by_id = {
                company["id"]: company for company in (companies_result.data or [])
            }
        for job in jobs_with_scores:
            job["companies"] = companies_by_id.get(job.get("company_id"), {})
        return jobs_with_scores

    except Exception as e:
        print(f"Error finding similar jobs: {e}")
        return []


def score_with_llama(
    resume_text: str,
    jobs: List[Dict],
    max_jobs: int = 20
) -> Tuple[List[Dict], int]:
    """Score top jobs with Llama-3 via Groq API."""
    scorer = GroqClient()
    scored_jobs = []
    failed_count = 0
    request_delay = float(os.getenv("GROQ_REQUEST_DELAY_SECONDS", "2.5"))
    
    print(f"Scoring top {min(len(jobs), max_jobs)} jobs with Groq...")
    
    for job in tqdm(jobs[:max_jobs], desc="Groq scoring"):
        try:
            result = scorer.score_job_relevance(
                resume_text=resume_text,
                job_title=job.get("title", ""),
                job_description=job.get("description", ""),
                company=job.get("companies", {}).get("employer_name", "")
            )

            if not result.get("success", True):
                failed_count += 1
                error = result.get("error", "unknown scoring error")
                print(
                    f"Deferred job {job.get('id')} ({job.get('title', 'untitled')}) "
                    f"for retry: {error[:160]}"
                )
                continue

            job["llama_score"] = result["score"]
            job["llama_reasoning"] = result["reasoning"]
            job["key_matches"] = result.get("key_matches", [])
            scored_jobs.append(job)

            # Leave headroom for retries within provider rate limits.
            time.sleep(request_delay)

        except Exception as e:
            print(f"Error scoring job {job.get('id')}: {e}")
            continue
    
    # Sort by Llama score
    scored_jobs.sort(key=lambda x: x.get("llama_score", 0), reverse=True)
    
    return scored_jobs, failed_count


def save_matches(resume_id: int, scored_jobs: List[Dict]) -> int:
    """Save job matches to database."""
    client = get_supabase_client()
    saved_count = 0
    
    for job in scored_jobs:
        match_data = {
            "job_id": job["id"],
            "resume_id": resume_id,
            "cosine_similarity": job.get("cosine_similarity", 0),
            "llama_score": job.get("llama_score", 0),
            "llama_reasoning": job.get("llama_reasoning", "")
        }
        
        result = client.insert_job_match(match_data)
        if result:
            saved_count += 1
    
    return saved_count


def match_resume_profile(resume: Dict) -> bool:
    """Run retrieval and scoring for one resume profile."""
    profile_name = resume.get("profile_name", "Default")
    print("=" * 60)
    print(f"Job Matching Pipeline — {profile_name}")
    print("=" * 60)

    resume_text = resume.get("resume_text", "")
    resume_embedding = resume.get("embedding")
    
    # Parse resume embedding if it's a string
    if isinstance(resume_embedding, str):
        import ast
        try:
            resume_embedding = ast.literal_eval(resume_embedding)
        except:
            print("Error parsing resume embedding, regenerating...")
            resume_embedding = None
    
    # Generate embedding if not exists
    if not resume_embedding:
        print("Generating resume embedding...")
        embedding_service = get_embedding_service()
        resume_embedding = embedding_service.encode(resume_text)
        
        # Update resume with embedding
        client = get_supabase_client()
        client.client.table("user_resume").update({
            "embedding": resume_embedding
        }).eq("id", resume["id"]).execute()
    
    # 2. Find similar jobs
    print("\n[2/5] Finding similar jobs using vector search...")
    match_threshold = float(os.getenv("MATCH_THRESHOLD", "0.4"))
    similar_jobs = find_similar_jobs(
        resume_embedding,
        limit=50,
        threshold=match_threshold,
    )
    print(
        f"Retrieval results: {len(similar_jobs)} candidates "
        f"at similarity >= {match_threshold:.2f}"
    )
    if similar_jobs:
        similarities = [job.get("cosine_similarity", 0) for job in similar_jobs]
        print(
            f"Similarity range: {min(similarities):.3f} to "
            f"{max(similarities):.3f}"
        )
    
    if not similar_jobs:
        print("No jobs found. Make sure jobs are scraped and embedded.")
        return False
    
    # 3. Score with Llama
    print("\n[3/5] Scoring jobs with Groq...")
    max_jobs = int(os.getenv("MAX_DAILY_MATCHES", "20"))
    scored_jobs, failed_count = score_with_llama(
        resume_text,
        similar_jobs,
        max_jobs=max_jobs,
    )
    print(
        f"Scoring results: {len(scored_jobs)} succeeded, "
        f"{failed_count} deferred for retry"
    )
    
    # 4. Save matches
    print("\n[4/5] Saving matches to database...")
    saved_count = save_matches(resume["id"], scored_jobs)
    print(f"Saved {saved_count} matches")
    
    # 5. Display top matches
    print("\n[5/5] Top 10 Matches:")
    print("=" * 60)
    
    for i, job in enumerate(scored_jobs[:10], 1):
        company = job.get("companies", {})
        print(f"\n{i}. {job.get('title')} at {company.get('employer_name')}")
        print(f"   Score: {job.get('llama_score')}/100")
        print(f"   Location: {job.get('location')}")
        print(f"   Approval Rate: {company.get('approval_rate', 0):.1f}%")
        print(f"   Reasoning: {job.get('llama_reasoning', '')[:100]}...")
        print(f"   URL: {job.get('job_url')}")
    
    print("\n" + "=" * 60)
    print("✅ Matching pipeline completed!")
    print(f"Total matches: {saved_count}")
    min_score = int(os.getenv("MIN_RELEVANCE_SCORE", "80"))
    print(
        f"Matches meeting notification threshold (>={min_score}): "
        f"{sum(1 for j in scored_jobs if j.get('llama_score', 0) >= min_score)}"
    )
    return bool(scored_jobs)


def main(profile_name: Optional[str] = None) -> bool:
    """Run matching for one named profile or every active profile."""
    print("\n[1/5] Fetching resume profiles...")
    resumes = get_resume_profiles(profile_name)
    if not resumes:
        return False
    outcomes = [match_resume_profile(resume) for resume in resumes]
    return all(outcomes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        help="Match only this resume profile; defaults to all active profiles",
    )
    args = parser.parse_args()
    raise SystemExit(0 if main(args.profile) else 1)
