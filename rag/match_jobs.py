"""
Main job matching pipeline using RAG (pgvector + Llama-3).
"""
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client
from rag.embedding_service import get_embedding_service
from agents.groq_client import GroqClient


def get_resume_data() -> Optional[Dict]:
    """Get user resume from database."""
    client = get_supabase_client()
    
    try:
        result = client.client.table("user_resume").select("*").limit(1).execute()
        if result.data:
            return result.data[0]
        else:
            print("No resume found in database. Please upload your resume first.")
            return None
    except Exception as e:
        print(f"Error fetching resume: {e}")
        return None


def find_similar_jobs(resume_embedding: List[float], limit: int = 50) -> List[Dict]:
    """Find similar jobs using vector similarity search."""
    client = get_supabase_client()
    
    # Note: This requires a custom RPC function in Supabase
    # For now, we'll use a simpler approach
    try:
        # Get all job embeddings and calculate similarity in Python
        # In production, this should be done via Supabase RPC for efficiency
        result = client.client.table("job_embeddings").select(
            "id, job_id, embedding"
        ).execute()
        
        if not result.data:
            print("No job embeddings found")
            return []
        
        # Calculate cosine similarity
        import numpy as np
        import json
        import ast
        
        resume_vec = np.array(resume_embedding, dtype=float)
        similarities = []
        
        for item in result.data:
            # Handle both list and string formats
            embedding = item["embedding"]
            if isinstance(embedding, str):
                try:
                    # Try JSON first
                    embedding = json.loads(embedding)
                except:
                    try:
                        # Try ast.literal_eval for Python list strings
                        embedding = ast.literal_eval(embedding)
                    except:
                        print(f"Warning: Could not parse embedding for job {item['job_id']}")
                        continue
            
            job_vec = np.array(embedding, dtype=float)
            
            # Calculate cosine similarity
            similarity = np.dot(resume_vec, job_vec) / (
                np.linalg.norm(resume_vec) * np.linalg.norm(job_vec)
            )
            similarities.append({
                "job_id": item["job_id"],
                "similarity": float(similarity)
            })
        
        # Sort by similarity and get top N
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        top_jobs = similarities[:limit]
        
        # Fetch full job details
        job_ids = [j["job_id"] for j in top_jobs]
        jobs_result = client.client.table("jobs").select(
            "*, companies(employer_name, approval_rate, total_approvals)"
        ).in_("id", job_ids).execute()
        
        # Merge similarity scores
        jobs_with_scores = []
        for job in jobs_result.data:
            sim = next((s for s in top_jobs if s["job_id"] == job["id"]), None)
            if sim:
                job["cosine_similarity"] = sim["similarity"]
                jobs_with_scores.append(job)
        
        return jobs_with_scores
        
    except Exception as e:
        print(f"Error finding similar jobs: {e}")
        return []


def score_with_llama(
    resume_text: str,
    jobs: List[Dict],
    max_jobs: int = 20
) -> List[Dict]:
    """Score top jobs with Llama-3 via Groq API."""
    scorer = GroqClient()
    scored_jobs = []
    
    print(f"Scoring top {min(len(jobs), max_jobs)} jobs with Groq Llama-3...")
    
    for job in tqdm(jobs[:max_jobs], desc="Groq scoring"):
        try:
            result = scorer.score_job_relevance(
                resume_text=resume_text,
                job_title=job.get("title", ""),
                job_description=job.get("description", ""),
                company=job.get("companies", {}).get("employer_name", "")
            )

            job["llama_score"] = result["score"]
            job["llama_reasoning"] = result["reasoning"]
            job["key_matches"] = result.get("key_matches", [])
            scored_jobs.append(job)

            # Respect Groq free tier rate limit (30 req/min)
            time.sleep(2)

        except Exception as e:
            print(f"Error scoring job {job.get('id')}: {e}")
            continue
    
    # Sort by Llama score
    scored_jobs.sort(key=lambda x: x.get("llama_score", 0), reverse=True)
    
    return scored_jobs


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
            "llama_reasoning": job.get("llama_reasoning", ""),
            "is_notified": False
        }
        
        result = client.insert_job_match(match_data)
        if result:
            saved_count += 1
    
    return saved_count


def main():
    """Main matching pipeline."""
    print("=" * 60)
    print("Job Matching Pipeline")
    print("=" * 60)
    
    # 1. Get resume
    print("\n[1/5] Fetching resume...")
    resume = get_resume_data()
    if not resume:
        return
    
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
    similar_jobs = find_similar_jobs(resume_embedding, limit=50)
    print(f"Found {len(similar_jobs)} similar jobs")
    
    if not similar_jobs:
        print("No jobs found. Make sure jobs are scraped and embedded.")
        return
    
    # 3. Score with Llama
    print("\n[3/5] Scoring jobs with Llama-3...")
    scored_jobs = score_with_llama(resume_text, similar_jobs, max_jobs=20)
    print(f"Scored {len(scored_jobs)} jobs")
    
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
    print(f"High-quality matches (>80): {sum(1 for j in scored_jobs if j.get('llama_score', 0) >= 80)}")


if __name__ == "__main__":
    main()
