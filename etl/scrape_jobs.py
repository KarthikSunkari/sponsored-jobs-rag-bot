"""
Hybrid job scraper: SerpAPI (primary) → Google Custom Search API → Selenium (fallback).
Uses the most reliable search method available.
"""
import sys
import time
import hashlib
import argparse
import json
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
from utils.job_location import assess_sponsorship_language, assess_us_job_location
from etl.ats_feeds import (
    deduplicate_jobs,
    discover_targets,
    fetch_all_targets,
    is_recent,
    load_seed_targets,
    matches_job_level,
    merge_targets,
    select_diverse_jobs,
)

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


ATS_URL_MARKERS = [
    "greenhouse.io", "ashbyhq.com", "lever.co", "myworkdayjobs.com",
    "jobvite.com", "smartrecruiters.com", "icims.com", "oraclecloud.com",
    "eightfold.ai", "apply.workable.com", "recruitee.com", "successfactors.com",
]


def load_search_queries() -> Dict:
    """Load search queries from YAML config."""
    config_path = Path(__file__).parent / "search_queries.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def google_search_jobs_api(query: str, max_results: int = 20) -> List[str]:
    """
    Search for jobs using Google Custom Search API.

    Args:
        query: Search query (full query string from YAML)
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
        results = api_client.search_jobs(query, max_results=max_results)
        urls = [
            r["link"] for r in results
            if r.get("link") and any(p in r["link"] for p in ATS_URL_MARKERS)
        ]

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
                    if any(platform in url for platform in ATS_URL_MARKERS):
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
            # Send the full YAML query directly to SerpAPI
            results = serpapi_client.search_jobs(query, num_results=max_results)

            # Filter to ATS platform URLs only
            urls = [
                r["link"] for r in results
                if r.get("link") and any(p in r["link"] for p in ATS_URL_MARKERS)
            ]

            if urls:
                print(f"✅ SerpAPI Success: {len(urls)} jobs found")
                return urls
            else:
                print("⚠️  SerpAPI returned no ATS results, trying Custom Search API...")
        except Exception as e:
            print(f"⚠️  SerpAPI error: {e}, trying Custom Search API...")
    else:
        print("⚠️  SerpAPI not configured, trying Custom Search API...")
    
    # Tier 2: Try Custom Search API
    api_client = get_google_search_client()
    if api_client.api_key and api_client.search_engine_id:
        print("🔍 Trying Custom Search API (Tier 2)...")
        try:
            # Send the full query directly
            results = api_client.search_jobs(query, max_results=max_results)

            # Filter to ATS platform URLs only
            urls = [
                r["link"] for r in results
                if r.get("link") and any(p in r["link"] for p in ATS_URL_MARKERS)
            ]

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


def _extract_greenhouse(url: str) -> Optional[Dict]:
    """Extract job details via Greenhouse public JSON API."""
    # URL format: https://boards.greenhouse.io/{company}/jobs/{id}
    try:
        parts = url.rstrip('/').split('/')
        job_id = parts[-1].split('?')[0]  # strip query params
        # Company slug is between greenhouse.io/ and /jobs/
        gh_index = next(i for i, p in enumerate(parts) if 'greenhouse.io' in p)
        company_slug = parts[gh_index + 1]

        api_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs/{job_id}"
        resp = requests.get(api_url, timeout=10)

        if resp.status_code != 200:
            return None

        data = resp.json()
        # Strip HTML tags from content
        content_html = data.get('content', '')
        description = BeautifulSoup(content_html, 'html.parser').get_text(separator=' ', strip=True)

        return {
            'title': data.get('title', ''),
            'company': data.get('company_name', company_slug.replace('-', ' ').title()),
            'location': data.get('location', {}).get('name', ''),
            'description': description,
            'source': 'greenhouse',
        }
    except Exception as e:
        print(f"  Greenhouse API error: {e}")
        return None


def _extract_ashby(url: str) -> Optional[Dict]:
    """Extract job details via Ashby GraphQL API."""
    # URL format: https://jobs.ashbyhq.com/{org}/{job_id}
    try:
        parts = url.rstrip('/').split('/')
        # Handle /application suffix
        if parts[-1] == 'application':
            parts = parts[:-1]
        org_slug = parts[-2]
        job_id = parts[-1].split('?')[0]

        api_url = 'https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting'
        payload = {
            'operationName': 'ApiJobPosting',
            'variables': {
                'organizationHostedJobsPageName': org_slug,
                'jobPostingId': job_id,
            },
            'query': '''query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {
                jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) {
                    id title descriptionHtml locationName
                }
            }'''
        }
        resp = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)

        if resp.status_code != 200:
            return None

        posting = resp.json().get('data', {}).get('jobPosting')
        if not posting:
            return None

        description = BeautifulSoup(posting.get('descriptionHtml', ''), 'html.parser').get_text(separator=' ', strip=True)

        return {
            'title': posting.get('title', ''),
            'company': org_slug.replace('-', ' ').title(),
            'location': posting.get('locationName', ''),
            'description': description,
            'source': 'ashby',
        }
    except Exception as e:
        print(f"  Ashby API error: {e}")
        return None


def _extract_lever(url: str) -> Optional[Dict]:
    """Extract job details from Lever (server-rendered HTML)."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        # Strip /apply suffix for the posting page
        clean_url = url.split('/apply')[0]
        resp = requests.get(clean_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')

        # Title is an h2 inside div.posting-headline, or a standalone h2
        headline_div = soup.find('div', class_='posting-headline')
        title_el = headline_div.find('h2') if headline_div else soup.find('h2')
        title = title_el.get_text(strip=True) if title_el else None

        # Company from URL path: jobs.lever.co/{company}/...
        url_parts = clean_url.split('/')
        company_slug = url_parts[3] if len(url_parts) > 3 else ''
        company = company_slug.replace('-', ' ').title()

        # Location from posting-categories
        location_el = soup.find('div', class_='location')
        location = location_el.get_text(strip=True) if location_el else ''

        # Description from the content sections
        content = soup.find('div', class_='content')
        description = content.get_text(separator=' ', strip=True) if content else ''

        return {
            'title': title or '',
            'company': company or '',
            'location': location,
            'description': description,
            'source': 'lever',
        }
    except Exception as e:
        print(f"  Lever parse error: {e}")
        return None


def _extract_html_generic(url: str) -> Optional[Dict]:
    """Generic HTML extraction for Workday, Jobvite, SmartRecruiters, iCIMS, etc."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')

        # Prefer schema.org JobPosting data when custom/enterprise career
        # sites expose it. This covers many Oracle, Eightfold, Workable, and
        # custom portals without brittle CSS selectors.
        for script in soup.find_all('script', {'type': 'application/ld+json'}):
            try:
                payload = json.loads(script.string or script.get_text() or '{}')
                candidates = payload if isinstance(payload, list) else [payload]
                if isinstance(payload, dict) and isinstance(payload.get('@graph'), list):
                    candidates.extend(payload['@graph'])
                posting = next(
                    (
                        item for item in candidates
                        if isinstance(item, dict)
                        and item.get('@type') == 'JobPosting'
                    ),
                    None,
                )
                if not posting:
                    continue

                organization = posting.get('hiringOrganization') or {}
                raw_locations = posting.get('jobLocation') or []
                if isinstance(raw_locations, dict):
                    raw_locations = [raw_locations]
                locations = []
                for raw_location in raw_locations:
                    address = (raw_location or {}).get('address') or {}
                    if isinstance(address, str):
                        locations.append(address)
                    else:
                        locations.append(', '.join(filter(None, [
                            address.get('addressLocality'),
                            address.get('addressRegion'),
                            address.get('addressCountry'),
                        ])))
                return {
                    'title': posting.get('title', ''),
                    'company': organization.get('name', '') if isinstance(organization, dict) else '',
                    'location': '; '.join(filter(None, locations)),
                    'description': BeautifulSoup(
                        posting.get('description', ''), 'html.parser'
                    ).get_text(' ', strip=True),
                    'posted_date': posting.get('datePosted'),
                    'source': 'structured_job_posting',
                }
            except (TypeError, ValueError, StopIteration):
                continue

        title = None
        company = None
        location = None
        description = None
        source = 'generic'

        if 'myworkdayjobs.com' in url:
            source = 'workday'
            title_el = soup.find('h2', {'data-automation-id': 'jobPostingHeader'})
            title = title_el.get_text(strip=True) if title_el else None
            loc_el = soup.find('div', {'data-automation-id': 'locations'})
            location = loc_el.get_text(strip=True) if loc_el else ''
            desc_el = soup.find('div', {'data-automation-id': 'jobPostingDescription'})
            description = desc_el.get_text(separator=' ', strip=True) if desc_el else ''
            company_match = url.split('//')[1].split('.')[0]
            company = company_match.replace('-', ' ').title()
        elif 'smartrecruiters.com' in url:
            source = 'smartrecruiters'
            # SmartRecruiters is JS-rendered; extract from <title> and URL
            # URL format: jobs.smartrecruiters.com/{Company}/{id}-{title}
            title_tag = soup.find('title')
            page_title = title_tag.get_text(strip=True) if title_tag else ''
            # Title tag format: "Job Title | SmartRecruiters"
            title = page_title.split('|')[0].strip() if '|' in page_title else page_title
            url_parts = url.split('/')
            company = url_parts[3] if len(url_parts) > 3 else ''
            company = company.replace('-', ' ')
            # Get whatever text is on the page for description
            body_text = soup.get_text(separator=' ', strip=True)
            description = body_text[:3000] if body_text else ''
        else:
            title_el = soup.find('h1') or soup.find('h2')
            title = title_el.get_text(strip=True) if title_el else None
            desc_el = soup.find('div', class_='description') or soup.find('div', class_='content')
            description = desc_el.get_text(separator=' ', strip=True) if desc_el else ''

            if 'jobvite.com' in url:
                source = 'jobvite'
            elif 'icims.com' in url:
                source = 'icims'

        return {
            'title': title or '',
            'company': company or '',
            'location': location or '',
            'description': description or '',
            'source': source,
        }
    except Exception as e:
        print(f"  HTML parse error: {e}")
        return None


def extract_job_details(url: str) -> Optional[Dict]:
    """
    Extract job details from ATS platform URL.
    Uses platform-specific APIs where available (Greenhouse, Ashby),
    falls back to HTML parsing for others (Lever, Workday, etc.).
    """
    try:
        # Route to the best extraction method per platform
        if 'greenhouse.io' in url:
            result = _extract_greenhouse(url)
        elif 'ashbyhq.com' in url:
            result = _extract_ashby(url)
        elif 'lever.co' in url:
            result = _extract_lever(url)
        else:
            result = _extract_html_generic(url)

        if not result or not result.get('title'):
            return None

        # Add common fields
        result['job_url'] = url
        result['url_hash'] = hashlib.md5(url.encode()).hexdigest()
        result['scraped_at'] = datetime.now().isoformat()

        return result

    except Exception as e:
        print(f"Error extracting {url}: {e}")
        return None


def get_or_create_company(client, company_name: str) -> Optional[Dict]:
    """Get or create company, linking to DOL sponsorship data via fuzzy match."""
    if not company_name:
        return None

    normalized_name = company_name.strip().upper()

    # 1. Try exact match (uppercase)
    existing = client.get_company_by_name(normalized_name)
    if existing:
        return existing

    # 2. Try exact match (original case)
    existing = client.get_company_by_name(company_name)
    if existing:
        return existing

    # 3. Fuzzy match: search DOL data for companies starting with this name
    #    e.g., "Visa" → "VISA TECHNOLOGY & OPERATIONS LLC" (563 approvals)
    try:
        result = client.client.table("companies").select(
            "id, employer_name, total_approvals, approval_rate"
        ).ilike("employer_name", f"{normalized_name}%").gt(
            "total_approvals", 0
        ).order("total_approvals", desc=True).limit(1).execute()

        if result.data:
            return result.data[0]
    except Exception:
        pass

    # 4. No match found — create new entry
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

        # Existing search-discovered URLs may contain tracking parameters,
        # while direct feeds return canonical URLs. Reuse the ATS posting ID
        # to avoid inserting the same requisition under both variants.
        source_job_id = str(job_data.get('source_job_id') or '')
        if source_job_id:
            identity_match = client.client.table("jobs").select("id").like(
                "job_url", f"%{source_job_id}%"
            ).limit(1).execute()
            if identity_match.data:
                print(f"  ⏭️  Already exists by ATS ID: {job_data['title']}")
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
            'posted_date': job_data.get('posted_date'),
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


def get_known_feed_jobs() -> List[Dict]:
    """Load prior ATS URLs so their complete public boards can be polled."""
    try:
        client = get_supabase_client()
        result = client.client.table("jobs").select(
            "job_url, companies(employer_name, total_approvals)"
        ).execute()
        return result.data or []
    except Exception as exc:
        print(f"⚠️  Could not discover prior ATS boards: {exc}")
        return []


def collect_direct_feed_jobs(level: str, lookback_days: int) -> List[Dict]:
    """Fetch structured feeds from curated and previously discovered boards."""
    seed_targets = load_seed_targets()
    discovered_targets = discover_targets(get_known_feed_jobs())
    targets = merge_targets(seed_targets, discovered_targets)
    print(
        f"Polling {len(targets)} direct ATS boards "
        f"({len(seed_targets)} curated, {len(discovered_targets)} discovered)..."
    )
    jobs, errors = fetch_all_targets(targets)
    print(f"Direct feeds returned {len(jobs)} published jobs; {len(errors)} board error(s)")

    filtered = []
    for job in jobs:
        if not matches_job_level(job.get("title", ""), level):
            continue
        if not is_recent(job, lookback_days):
            continue
        eligible, reason = assess_us_job_location(
            job.get("location", ""), job.get("description", "")
        )
        if not eligible:
            continue
        sponsor_eligible, sponsor_reason = assess_sponsorship_language(
            job.get("description", "")
        )
        if not sponsor_eligible:
            continue
        filtered.append(job)
    print(
        f"Direct feeds retained {len(filtered)} recent, US-eligible, "
        f"early/mid-career engineering jobs"
    )
    return filtered


def scrape_jobs(
    level: str,
    max_jobs: int = 20,
    headless: bool = True,
    lookback_days: int = 7,
) -> int:
    """Fetch direct ATS feeds, then use search to discover additional boards."""
    print("=" * 60)
    print(f"Hybrid Job Scraper - {level.upper()}")
    print("=" * 60)
    
    config = load_search_queries()
    
    if level not in {"newgrad", "midlevel", "all"}:
        print(f"❌ Invalid level: {level}")
        return 0

    print(f"\n[1/4] Polling direct ATS feeds (past {lookback_days} days)...")
    direct_jobs = collect_direct_feed_jobs(level, lookback_days)

    print("\n[2/4] Searching for newly discovered ATS postings...")
    levels = ["newgrad", "midlevel"] if level == "all" else [level]
    job_urls = []
    for search_level in levels:
        query = config[search_level]['query']
        job_urls.extend(
            google_search_jobs(query, max_results=max_jobs, headless=headless)
        )
    job_urls = list(dict.fromkeys(job_urls))
    print(f"Found {len(job_urls)} job URLs")

    print("\n[3/4] Extracting search results and combining sources...")
    searched_jobs = []
    for url in tqdm(job_urls[:max_jobs], desc="Extracting"):
        job_data = extract_job_details(url)
        if job_data:
            if not matches_job_level(job_data.get("title", ""), level):
                continue
            eligible, reason = assess_us_job_location(
                job_data.get("location", ""),
                job_data.get("description", ""),
            )
            if eligible:
                sponsor_eligible, sponsor_reason = assess_sponsorship_language(
                    job_data.get("description", "")
                )
                if sponsor_eligible:
                    searched_jobs.append(job_data)
                else:
                    print(
                        f"  🛂 Skipped non-sponsoring role: "
                        f"{job_data.get('title', 'Untitled')} — {sponsor_reason}"
                    )
            else:
                print(
                    f"  🌎 Skipped non-US role: {job_data.get('title', 'Untitled')} "
                    f"({job_data.get('location', 'unknown')}) — {reason}"
                )
        time.sleep(1)

    jobs = deduplicate_jobs(direct_jobs + searched_jobs)
    jobs = select_diverse_jobs(jobs, max_jobs=max_jobs, max_per_company=10)
    print(
        f"Combined {len(direct_jobs)} feed jobs and {len(searched_jobs)} "
        f"search jobs into {len(jobs)} unique candidates"
    )

    if not jobs:
        print("❌ No eligible jobs found from feeds or search")
        return 0

    print("\n[4/4] Saving to database...")
    saved_count = 0
    for job in tqdm(jobs, desc="Saving"):
        if save_job_to_db(job):
            saved_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ Completed!")
    print(f"URLs found: {len(job_urls)}")
    print(f"Direct-feed candidates: {len(direct_jobs)}")
    print(f"Jobs extracted: {len(jobs)}")
    print(f"Jobs saved: {saved_count}")
    print(f"Duplicates: {len(jobs) - saved_count}")
    print("=" * 60)
    return len(jobs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hybrid Google job scraper (API + Selenium)")
    parser.add_argument(
        "--level", type=str, required=True,
        choices=["newgrad", "midlevel", "all"],
    )
    parser.add_argument("--max-jobs", type=int, default=20)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--show-browser", action="store_true")
    
    args = parser.parse_args()
    extracted_count = scrape_jobs(
        args.level,
        args.max_jobs,
        headless=not args.show_browser,
        lookback_days=args.lookback_days,
    )
    raise SystemExit(0 if extracted_count else 1)
