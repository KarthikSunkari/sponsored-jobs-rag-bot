"""
Hybrid job scraper: SerpAPI (primary) → Google Custom Search API → Selenium (fallback).
Uses the most reliable search method available.
"""
import sys
import time
import hashlib
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import yaml
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client
from rag.embedding_service import get_embedding_service
from utils.serpapi_client import get_serpapi_client
from utils.google_search import get_google_search_client

# Import Selenium components (only used as fallback)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️  Selenium not available, will use API only")


def load_search_queries() -> Dict:
    """Load search queries from YAML config."""
    config_path = Path(__file__).parent / "search_queries.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def google_search_jobs_api(query: str, max_results: int = 20) -> List[str]:
    """
    Search for jobs using Google Custom Search API.
    
    Args:
        query: Search query
        max_results: Maximum results
        
    Returns:
        List of job URLs
    """
    print(f"🔍 Searching with Google Custom Search API...")
    
    api_client = get_google_search_client()
    
    if not api_client.api_key or not api_client.search_engine_id:
        print("⚠️  API not configured, will use Selenium fallback")
        return []
    
    try:
        # Extract role and level from query
        # Query format: "(site:...) software engineer newgrad"
        parts = query.split(")")
        if len(parts) > 1:
            role_level = parts[1].strip()
            role_parts = role_level.rsplit(' ', 1)
            if len(role_parts) == 2:
                role, level = role_parts
            else:
                role = role_level
                level = "newgrad"
        else:
            role = "software engineer"
            level = "newgrad"
        
        urls = api_client.search_jobs_ats_platforms(role, level, max_results=max_results)
        
        if urls:
            print(f"✅ Found {len(urls)} job URLs via API")
            return urls
        else:
            print("⚠️  No results from API, will try Selenium fallback")
            return []
            
    except Exception as e:
        print(f"⚠️  API error: {e}")
        print("Will use Selenium fallback...")
        return []


def setup_selenium_driver(headless: bool = True) -> Optional[webdriver.Chrome]:
    """Set up Selenium Chrome/Chromium driver."""
    if not SELENIUM_AVAILABLE:
        return None
    
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless=new")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
    chrome_options.add_argument("--disable-gpu")
    
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    try:
        # Try Chromium first (Docker/Linux)
        import shutil
        chromium_path = shutil.which("chromium")
        chromedriver_path = shutil.which("chromedriver")
        
        if chromium_path and chromedriver_path:
            # Use system Chromium and ChromeDriver
            chrome_options.binary_location = chromium_path
            service = Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print(f"✅ Using Chromium: {chromium_path}")
        else:
            # Fall back to webdriver-manager (macOS)
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            print("✅ Using Chrome via webdriver-manager")
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"⚠️  Could not initialize Selenium: {e}")
        return None


def google_search_jobs_selenium(query: str, max_results: int = 20, headless: bool = True) -> List[str]:
    """Selenium fallback for Google search."""
    if not SELENIUM_AVAILABLE:
        print("❌ Selenium not available")
        return []
    
    print(f"🌐 Searching with Selenium (fallback)...")
    job_urls = []
    
    driver = setup_selenium_driver(headless)
    if not driver:
        return []
    
    try:
        search_url = f"https://www.google.com/search?q={query}&tbs=qdr:d&num={max_results}"
        driver.get(search_url)
        time.sleep(2)
        
        search_results = driver.find_elements(By.CSS_SELECTOR, "div.g a")
        
        for result in search_results:
            try:
                url = result.get_attribute("href")
                if url and url.startswith("http") and "google.com" not in url:
                    if any(platform in url for platform in [
                        "greenhouse.io", "ashbyhq.com", "lever.co",
                        "myworkdayjobs.com", "jobvite.com", "smartrecruiters.com", "icims.com"
                    ]):
                        job_urls.append(url)
                        if len(job_urls) >= max_results:
                            break
            except:
                continue
        
        print(f"✅ Found {len(job_urls)} job URLs via Selenium")
        
    except Exception as e:
        print(f"❌ Selenium error: {e}")
    finally:
        if driver:
            driver.quit()
    
    return job_urls


def google_search_jobs(query: str, max_results: int = 20, headless: bool = True) -> List[str]:
    """
    Hybrid search with 3-tier fallback:
    1. SerpAPI (most reliable, 100 free/month)
    2. Google Custom Search API (100 free/day)
    3. Selenium (unlimited but may be blocked)
    
    Args:
        query: Search query
        max_results: Maximum results
        headless: Headless mode for Selenium fallback
        
    Returns:
        List of job URLs
    """
    # Tier 1: Try SerpAPI first (most reliable)
    serpapi_client = get_serpapi_client()
    if serpapi_client.api_key:
        print("🔍 Trying SerpAPI (Tier 1 - Most Reliable)...")
        try:
            # Extract role and level from query
            parts = query.split(")")
            if len(parts) > 1:
                role_level = parts[1].strip()
                role_parts = role_level.rsplit(' ', 1)
                if len(role_parts) == 2:
                    role, level = role_parts
                else:
                    role = role_level
                    level = "newgrad"
            else:
                role = "software engineer"
                level = "newgrad"
            
            urls = serpapi_client.search_jobs_ats_platforms(role, level, max_results=max_results)
            
            if urls:
                print(f"✅ SerpAPI Success: {len(urls)} jobs found")
                return urls
            else:
                print("⚠️  SerpAPI returned no results, trying Custom Search API...")
        except Exception as e:
            print(f"⚠️  SerpAPI error: {e}, trying Custom Search API...")
    else:
        print("⚠️  SerpAPI not configured, trying Custom Search API...")
    
    # Tier 2: Try Custom Search API
    api_client = get_google_search_client()
    if api_client.api_key and api_client.search_engine_id:
        print("🔍 Trying Custom Search API (Tier 2)...")
        try:
            parts = query.split(")")
            if len(parts) > 1:
                role_level = parts[1].strip()
                role_parts = role_level.rsplit(' ', 1)
                if len(role_parts) == 2:
                    role, level = role_parts
                else:
                    role = role_level
                    level = "newgrad"
            else:
                role = "software engineer"
                level = "newgrad"
            
            urls = api_client.search_jobs_ats_platforms(role, level, max_results=max_results)
            
            if urls:
                print(f"✅ Custom Search API Success: {len(urls)} jobs found")
                return urls
            else:
                print("⚠️  Custom Search API returned no results, trying Selenium...")
        except Exception as e:
            print(f"⚠️  Custom Search API error: {e}, trying Selenium...")
    else:
        print("⚠️  Custom Search API not configured, trying Selenium...")
    
    # Tier 3: Fallback to Selenium
    print("🔍 Using Selenium (Tier 3 - Fallback)...")
    return google_search_jobs_selenium(query, max_results, headless)


def extract_job_details(url: str) -> Optional[Dict]:
    """Extract job details from ATS platform URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        job_data = {
            'job_url': url,
            'url_hash': hashlib.md5(url.encode()).hexdigest(),
            'scraped_at': datetime.now().isoformat()
        }
        
        # Platform-specific extraction (same as before)
        if 'greenhouse.io' in url:
            job_data['source'] = 'greenhouse'
            job_data['title'] = soup.find('h1', class_='app-title')
            job_data['company'] = soup.find('span', class_='company-name')
            job_data['location'] = soup.find('div', class_='location')
            job_data['description'] = soup.find('div', id='content')
        elif 'ashbyhq.com' in url:
            job_data['source'] = 'ashby'
            job_data['title'] = soup.find('h2', class_='ashby-job-posting-heading')
            job_data['company'] = soup.find('div', class_='ashby-company-name')
            job_data['location'] = soup.find('div', class_='ashby-job-posting-location')
            job_data['description'] = soup.find('div', class_='ashby-job-posting-description')
        elif 'lever.co' in url:
            job_data['source'] = 'lever'
            job_data['title'] = soup.find('h2', class_='posting-headline')
            job_data['company'] = soup.find('div', class_='main-header-text-logo')
            job_data['location'] = soup.find('div', class_='posting-categories')
            job_data['description'] = soup.find('div', class_='content')
        elif 'myworkdayjobs.com' in url:
            job_data['source'] = 'workday'
            job_data['title'] = soup.find('h2', {'data-automation-id': 'jobPostingHeader'})
            job_data['location'] = soup.find('div', {'data-automation-id': 'locations'})
            job_data['description'] = soup.find('div', {'data-automation-id': 'jobPostingDescription'})
            company_match = url.split('//')[1].split('.')[0]
            job_data['company'] = company_match.replace('-', ' ').title()
        else:
            job_data['source'] = 'generic'
            job_data['title'] = soup.find('h1') or soup.find('h2')
            job_data['description'] = soup.find('div', class_='description') or soup.find('div', class_='content')
        
        # Convert to text
        for field in ['title', 'company', 'location', 'description']:
            if job_data.get(field) and hasattr(job_data[field], 'get_text'):
                job_data[field] = job_data[field].get_text(strip=True)
        
        if not job_data.get('title') or not job_data.get('description'):
            return None
        
        return job_data
        
    except Exception as e:
        print(f"Error extracting {url}: {e}")
        return None


def get_or_create_company(client, company_name: str) -> Optional[Dict]:
    """Get or create company with sponsorship data."""
    if not company_name:
        return None
    
    normalized_name = company_name.strip().upper()
    existing = client.get_company_by_name(normalized_name)
    if existing:
        return existing
    
    existing = client.get_company_by_name(company_name)
    if existing:
        return existing
    
    company_data = {
        'employer_name': company_name,
        'total_approvals': 0,
        'total_denials': 0
    }
    return client.insert_company(company_data)


def save_job_to_db(job_data: Dict) -> bool:
    """Save job to database with embedding."""
    try:
        client = get_supabase_client()
        
        existing = client.client.table("jobs").select("id").eq(
            "url_hash", job_data['url_hash']
        ).execute()
        
        if existing.data:
            print(f"  ⏭️  Already exists: {job_data['title']}")
            return False
        
        company_data = None
        company_id = None
        if job_data.get('company'):
            company_data = get_or_create_company(client, job_data['company'])
            if company_data:
                company_id = company_data['id']
        
        job_record = {
            'company_id': company_id,
            'title': job_data['title'],
            'description': job_data.get('description', ''),
            'location': job_data.get('location', ''),
            'job_url': job_data['job_url'],
            'url_hash': job_data['url_hash'],
            'source': job_data.get('source', 'google_search'),
            'posted_date': None,
            'is_active': True
        }
        
        result = client.insert_job(job_record)
        if not result:
            return False
        
        job_id = result['id']
        
        embedding_service = get_embedding_service()
        job_text = f"{job_data['title']} {job_data.get('description', '')}"
        embedding = embedding_service.encode(job_text)
        client.insert_job_embedding(job_id, embedding)
        
        sponsorship_note = ""
        if company_data and company_data.get('total_approvals', 0) > 0:
            approval_rate = company_data.get('approval_rate', 0)
            total_approvals = company_data.get('total_approvals', 0)
            sponsorship_note = f" [🟢 {total_approvals} approvals, {approval_rate:.1f}%]"
        
        print(f"  ✅ Saved: {job_data['title']} at {job_data.get('company', 'Unknown')}{sponsorship_note}")
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def scrape_jobs(level: str, max_jobs: int = 20, headless: bool = True):
    """Main scraping function with hybrid API/Selenium approach."""
    print("=" * 60)
    print(f"Hybrid Job Scraper - {level.upper()}")
    print("=" * 60)
    
    config = load_search_queries()
    
    if level not in config:
        print(f"❌ Invalid level: {level}")
        return
    
    query_config = config[level]
    query = query_config['query']
    
    print(f"\n[1/3] Searching for {level} jobs (past 24 hours)...")
    print(f"Strategy: API first, Selenium fallback")
    
    job_urls = google_search_jobs(query, max_results=max_jobs * 2, headless=headless)
    print(f"Found {len(job_urls)} job URLs")
    
    if not job_urls:
        print("❌ No jobs found")
        return
    
    print(f"\n[2/3] Extracting job details...")
    jobs = []
    for url in tqdm(job_urls[:max_jobs * 2], desc="Extracting"):
        job_data = extract_job_details(url)
        if job_data:
            jobs.append(job_data)
        time.sleep(1)
        
        if len(jobs) >= max_jobs:
            break
    
    print(f"Extracted {len(jobs)} jobs")
    
    print(f"\n[3/3] Saving to database...")
    saved_count = 0
    for job in tqdm(jobs, desc="Saving"):
        if save_job_to_db(job):
            saved_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ Completed!")
    print(f"URLs found: {len(job_urls)}")
    print(f"Jobs extracted: {len(jobs)}")
    print(f"Jobs saved: {saved_count}")
    print(f"Duplicates: {len(jobs) - saved_count}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid Google job scraper (API + Selenium)")
    parser.add_argument("--level", type=str, required=True, choices=["newgrad", "midlevel"])
    parser.add_argument("--max-jobs", type=int, default=20)
    parser.add_argument("--show-browser", action="store_true")
    
    args = parser.parse_args()
    scrape_jobs(args.level, args.max_jobs, headless=not args.show_browser)
