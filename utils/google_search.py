# Google Custom Search API Integration
# FREE tier: 100 queries/day (perfect for daily job scraping)
# More reliable than Selenium, no rate limiting, faster results

import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()


class GoogleCustomSearch:
    """
    Google Custom Search API client for job searching.
    
    Setup:
    1. Go to https://developers.google.com/custom-search/v1/overview
    2. Get API key: https://console.cloud.google.com/apis/credentials
    3. Create Custom Search Engine: https://programmablesearchengine.google.com/
    4. Configure to search the entire web
    5. Add API key and Search Engine ID to .env
    """
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        self.search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        self.base_url = "https://www.googleapis.com/customsearch/v1"
    
    def search_jobs(
        self, 
        query: str, 
        max_results: int = 10,
        date_restrict: str = "d1"  # d1 = past day, w1 = past week
    ) -> List[Dict]:
        """
        Search for jobs using Google Custom Search API.
        
        Args:
            query: Search query
            max_results: Maximum results to return (max 10 per request)
            date_restrict: Date restriction (d1=past day, w1=past week)
            
        Returns:
            List of search results with title, link, snippet
        """
        if not self.api_key or not self.search_engine_id:
            print("⚠️  Google Custom Search API not configured")
            print("Using Selenium fallback...")
            return []
        
        results = []
        
        try:
            params = {
                "key": self.api_key,
                "cx": self.search_engine_id,
                "q": query,
                "num": min(max_results, 10),  # Max 10 per request
                "dateRestrict": date_restrict
            }
            
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if "items" in data:
                for item in data["items"]:
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "displayLink": item.get("displayLink", "")
                    })
            
            print(f"✅ Found {len(results)} results via Google Custom Search API")
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Google Custom Search API error: {e}")
            return []
    
    def search_jobs_ats_platforms(
        self,
        role: str,
        level: str = "newgrad",
        max_results: int = 20
    ) -> List[str]:
        """
        Search for jobs on ATS platforms using Custom Search API.
        
        Args:
            role: Job role (e.g., "software engineer")
            level: Job level (newgrad, midlevel, senior)
            max_results: Maximum results
            
        Returns:
            List of job URLs
        """
        # ATS platforms
        ats_sites = [
            "site:boards.greenhouse.io",
            "site:jobs.ashbyhq.com",
            "site:jobs.lever.co",
            "site:myworkdayjobs.com",
            "site:jobvite.com",
            "site:smartrecruiters.com",
            "site:icims.com"
        ]
        
        # Build query
        site_query = " OR ".join(ats_sites)
        query = f"({site_query}) {role} {level}"
        
        print(f"🔍 Searching: {query}")
        
        results = self.search_jobs(query, max_results=max_results, date_restrict="d1")
        
        # Extract URLs
        job_urls = [r["link"] for r in results if r.get("link")]
        
        return job_urls


def get_google_search_client():
    """Get singleton Google Custom Search client."""
    return GoogleCustomSearch()


if __name__ == "__main__":
    # Test the API
    client = GoogleCustomSearch()
    
    if not client.api_key:
        print("\n" + "="*60)
        print("Google Custom Search API Setup Required")
        print("="*60)
        print("\n1. Get API Key:")
        print("   https://console.cloud.google.com/apis/credentials")
        print("\n2. Create Custom Search Engine:")
        print("   https://programmablesearchengine.google.com/")
        print("   - Enable 'Search the entire web'")
        print("   - Copy the Search Engine ID")
        print("\n3. Add to .env:")
        print("   GOOGLE_SEARCH_API_KEY=your-api-key")
        print("   GOOGLE_SEARCH_ENGINE_ID=your-search-engine-id")
        print("\n4. Free tier: 100 queries/day")
        print("="*60)
    else:
        # Test search
        urls = client.search_jobs_ats_platforms("software engineer", "newgrad", max_results=5)
        print(f"\nFound {len(urls)} job URLs:")
        for url in urls[:5]:
            print(f"  - {url}")
