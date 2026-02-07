# SerpAPI Integration - Reliable Google Search Alternative
# 100 free searches/month, no rate limiting, works perfectly

import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()


class SerpAPIClient:
    """
    SerpAPI client for reliable Google Search results.
    
    Why SerpAPI:
    - 100 free searches/month (perfect for daily scraping)
    - No rate limiting or blocking
    - Returns clean, structured JSON
    - Handles CAPTCHAs automatically
    - More reliable than Selenium or Custom Search API
    
    Setup:
    1. Sign up: https://serpapi.com/users/sign_up
    2. Get API key from dashboard
    3. Add to .env: SERPAPI_KEY=your-key-here
    """
    
    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY")
        self.base_url = "https://serpapi.com/search"
    
    def search_jobs(
        self,
        query: str,
        num_results: int = 20,
        time_filter: str = "qdr:d"  # qdr:d = past day, qdr:w = past week
    ) -> List[Dict]:
        """
        Search Google using SerpAPI.
        
        Args:
            query: Search query
            num_results: Number of results
            time_filter: Time filter (qdr:d for past day)
            
        Returns:
            List of search results with title, link, snippet
        """
        if not self.api_key:
            print("⚠️  SerpAPI not configured")
            return []
        
        try:
            params = {
                "engine": "google",
                "q": query,
                "api_key": self.api_key,
                "num": num_results,
                "tbs": time_filter,
                "gl": "us",  # Country: US
                "hl": "en"   # Language: English
            }
            
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            if "organic_results" in data:
                for item in data["organic_results"]:
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "position": item.get("position", 0)
                    })
            
            print(f"✅ SerpAPI: Found {len(results)} results")
            return results
            
        except Exception as e:
            print(f"❌ SerpAPI error: {e}")
            return []
    
    def search_jobs_ats_platforms(
        self,
        role: str,
        level: str = "newgrad",
        max_results: int = 20
    ) -> List[str]:
        """
        Search for jobs on ATS platforms using SerpAPI.
        
        Args:
            role: Job role
            level: Job level
            max_results: Max results
            
        Returns:
            List of job URLs
        """
        # Build query for ATS platforms
        ats_sites = [
            "site:boards.greenhouse.io",
            "site:jobs.ashbyhq.com",
            "site:jobs.lever.co",
            "site:myworkdayjobs.com",
            "site:jobvite.com",
            "site:smartrecruiters.com",
            "site:icims.com"
        ]
        
        site_query = " OR ".join(ats_sites)
        query = f"({site_query}) {role} {level}"
        
        print(f"🔍 SerpAPI Search: {query}")
        
        results = self.search_jobs(query, num_results=max_results, time_filter="qdr:d")
        
        # Extract job URLs
        job_urls = []
        for r in results:
            url = r.get("link", "")
            if url and any(platform in url for platform in [
                "greenhouse.io", "ashbyhq.com", "lever.co",
                "myworkdayjobs.com", "jobvite.com", "smartrecruiters.com", "icims.com"
            ]):
                job_urls.append(url)
        
        return job_urls


def get_serpapi_client():
    """Get singleton SerpAPI client."""
    return SerpAPIClient()


if __name__ == "__main__":
    # Test SerpAPI
    client = SerpAPIClient()
    
    if not client.api_key:
        print("\n" + "="*60)
        print("SerpAPI Setup Required")
        print("="*60)
        print("\n1. Sign up: https://serpapi.com/users/sign_up")
        print("2. Get API key from dashboard")
        print("3. Add to .env: SERPAPI_KEY=your-key-here")
        print("\n4. Free tier: 100 searches/month")
        print("   Perfect for daily job scraping!")
        print("="*60)
    else:
        # Test search
        urls = client.search_jobs_ats_platforms("software engineer", "newgrad", max_results=5)
        print(f"\n✅ Found {len(urls)} job URLs:")
        for url in urls[:5]:
            print(f"  - {url}")
