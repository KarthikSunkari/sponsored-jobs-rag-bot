"""
Supabase client utility with pgvector support.
"""
import os
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class SupabaseClient:
    """Wrapper for Supabase client with helper methods."""
    
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_KEY) must be set"
            )
        
        self.client: Client = create_client(url, key)
    
    def insert_company(self, company_data: Dict[str, Any]) -> Optional[Dict]:
        """Insert or update company sponsorship data."""
        try:
            result = self.client.table("companies").upsert(
                company_data,
                on_conflict="employer_name"
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error inserting company: {e}")
            return None

    def upsert_companies(self, companies: List[Dict[str, Any]]) -> int:
        """Upsert a batch of sponsorship companies."""
        try:
            result = self.client.table("companies").upsert(
                companies,
                on_conflict="employer_name"
            ).execute()
            return len(result.data or [])
        except Exception as e:
            print(f"Error upserting company batch: {e}")
            return 0

    def get_all_companies(self, page_size: int = 1000) -> List[Dict]:
        """Fetch all companies in pages for quarterly data merging."""
        companies = []
        start = 0
        while True:
            result = self.client.table("companies").select(
                "employer_name,naics_code,h1b_approvals,h1b_denials"
            ).range(start, start + page_size - 1).execute()
            page = result.data or []
            companies.extend(page)
            if len(page) < page_size:
                return companies
            start += page_size
    
    def get_company_by_name(self, employer_name: str) -> Optional[Dict]:
        """Get company by employer name."""
        try:
            result = self.client.table("companies").select("*").eq(
                "employer_name", employer_name
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error fetching company: {e}")
            return None
    
    def insert_job(self, job_data: Dict[str, Any]) -> Optional[Dict]:
        """Insert job listing."""
        try:
            result = self.client.table("jobs").insert(job_data).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error inserting job: {e}")
            return None
    
    def insert_job_embedding(self, job_id: int, embedding: List[float]) -> Optional[Dict]:
        """Insert job embedding vector."""
        try:
            result = self.client.table("job_embeddings").insert({
                "job_id": job_id,
                "embedding": embedding
            }).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error inserting embedding: {e}")
            return None
    
    def get_sponsorship_companies(self, min_approval_rate: float = 70.0) -> List[Dict]:
        """Get companies with good sponsorship track record."""
        try:
            result = self.client.table("sponsorship_companies").select("*").execute()
            return result.data
        except Exception as e:
            print(f"Error fetching sponsorship companies: {e}")
            return []
    
    def search_similar_jobs(
        self, 
        resume_embedding: List[float], 
        limit: int = 50,
        threshold: float = 0.4,
    ) -> List[Dict]:
        """Search for similar jobs using vector similarity."""
        try:
            # Using RPC for vector similarity search
            result = self.client.rpc(
                "match_jobs",
                {
                    "query_embedding": resume_embedding,
                    "match_threshold": threshold,
                    "match_count": limit
                }
            ).execute()
            return result.data
        except Exception as e:
            print(f"Error searching similar jobs: {e}")
            return []
    
    def insert_job_match(self, match_data: Dict[str, Any]) -> Optional[Dict]:
        """Insert or refresh a match for a resume/job pair."""
        try:
            result = self.client.table("job_matches").upsert(
                match_data,
                on_conflict="job_id,resume_id"
            ).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error inserting job match: {e}")
            return None
    
    def get_unnotified_matches(self, min_score: int = 80) -> List[Dict]:
        """Get high-scoring matches that haven't been notified."""
        try:
            result = self.client.table("active_matches").select("*").eq(
                "is_notified", False
            ).gte("llama_score", min_score).execute()
            matches = result.data or []

            # active_matches intentionally stays compact, but notification
            # eligibility also needs the full description for multi-country
            # postings whose short location label is incomplete.
            job_ids = list({match["job_id"] for match in matches if match.get("job_id")})
            if job_ids:
                jobs_result = self.client.table("jobs").select(
                    "id,description"
                ).in_("id", job_ids).execute()
                descriptions = {
                    job["id"]: job.get("description", "")
                    for job in (jobs_result.data or [])
                }
                for match in matches:
                    match["description"] = descriptions.get(match.get("job_id"), "")

            return matches
        except Exception as e:
            print(f"Error fetching unnotified matches: {e}")
            return []
    
    def mark_as_notified(self, match_ids: List[int]) -> bool:
        """Mark matches as notified."""
        try:
            self.client.table("job_matches").update({
                "is_notified": True
            }).in_("id", match_ids).execute()
            return True
        except Exception as e:
            print(f"Error marking as notified: {e}")
            return False


# Singleton instance
_supabase_client: Optional[SupabaseClient] = None


def get_supabase_client() -> SupabaseClient:
    """Get or create Supabase client singleton."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = SupabaseClient()
    return _supabase_client
