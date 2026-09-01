"""Direct public ATS feed ingestion and normalization.

Google/SerpAPI remains useful for discovering new job boards. Once a board is
known, these adapters pull its structured public feed directly so indexing lag
and search-result caps do not determine daily recall.
"""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

import requests
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


DEFAULT_TIMEOUT = 20
MAX_BOARD_LISTINGS = 500
SUPPORTED_PLATFORMS = {
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "workday",
}

_ENGINEERING_TITLE = re.compile(
    r"\b(?:software|backend|back-end|fullstack|full-stack|platform|infrastructure|"
    r"site reliability|sre|devops|cloud|data|machine learning|ml|ai|agentic|"
    r"application)\s+(?:development\s+)?(?:engineer|developer)|"
    r"\b(?:software developer|application developer|member of technical staff|mts|sde)\b",
    re.IGNORECASE,
)
_UPPER_LEVEL_TITLE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|architect|vp|vice president)\b",
    re.IGNORECASE,
)
_EARLY_CAREER_TITLE = re.compile(
    r"\b(?:new grad(?:uate)?|university|entry[- ]level|junior|associate|campus|"
    r"early career|graduate|engineer i|developer i|sde i|sde 1)\b",
    re.IGNORECASE,
)

_COMPANY_SUFFIX_WORDS = {
    "co", "company", "corp", "corporation", "inc", "incorporated", "international",
    "llc", "ltd", "limited", "plc", "software", "systems", "technologies",
    "technology", "group", "holdings", "energy", "labs",
}


@dataclass(frozen=True)
class FeedTarget:
    platform: str
    identifier: str
    company: str
    base_url: str = ""
    site: str = ""

    @property
    def key(self) -> Tuple[str, str, str]:
        return self.platform, self.identifier.lower(), self.site.lower()


def _board_company_key(value: str) -> str:
    """Reduce legal employer names and board slugs to a comparable brand key."""
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    return "".join(word for word in words if word not in _COMPANY_SUFFIX_WORDS)


def canonicalize_job_url(url: str) -> str:
    """Remove tracking/application variants without changing job identity."""
    parsed = urlparse((url or "").strip())
    path = re.sub(r"/(?:apply|application)/?$", "", parsed.path, flags=re.I)
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path.rstrip("/"), "", "", ""))


def matches_job_level(title: str, level: str = "all") -> bool:
    """Keep relevant early/mid-career engineering titles."""
    if not _ENGINEERING_TITLE.search(title or ""):
        return False
    if _UPPER_LEVEL_TITLE.search(title or ""):
        return False
    if level == "newgrad":
        return bool(_EARLY_CAREER_TITLE.search(title or ""))
    if level == "midlevel":
        return not bool(re.search(r"\b(?:intern|internship)\b", title or "", re.I))
    return not bool(re.search(r"\b(?:intern|internship)\b", title or "", re.I))


def _plain_text(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def _parse_datetime(value) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        parsed = date_parser.parse(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _relative_workday_date(value: str, now: Optional[datetime] = None) -> Optional[datetime]:
    now = now or datetime.now(timezone.utc)
    text = (value or "").strip().lower()
    if text in {"posted today", "today"}:
        return now
    if text in {"posted yesterday", "yesterday"}:
        return now - timedelta(days=1)
    match = re.search(r"posted\s+(\d+)\s+days?\s+ago", text)
    if match:
        return now - timedelta(days=int(match.group(1)))
    if "30+ days" in text:
        return now - timedelta(days=31)
    return _parse_datetime(value)


def _normalized_job(
    *,
    title: str,
    company: str,
    location: str,
    description: str,
    job_url: str,
    source: str,
    posted_date=None,
    source_job_id: str = "",
    source_board: str = "",
) -> Optional[Dict]:
    canonical_url = canonicalize_job_url(job_url)
    if not title or not canonical_url:
        return None
    posted = posted_date if isinstance(posted_date, datetime) else _parse_datetime(posted_date)
    return {
        "title": title.strip(),
        "company": (company or source_board).strip(),
        "location": (location or "").strip(),
        "description": _plain_text(description),
        "job_url": canonical_url,
        "url_hash": hashlib.md5(canonical_url.encode()).hexdigest(),
        "source": source,
        "posted_date": posted.isoformat() if posted else None,
        "source_job_id": str(source_job_id or ""),
        "source_board": source_board or "",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def load_seed_targets(path: Optional[Path] = None) -> List[FeedTarget]:
    path = path or Path(__file__).with_name("ats_feeds.yaml")
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text()) or {}
    targets = []
    for platform, entries in (payload.get("targets") or {}).items():
        if platform not in SUPPORTED_PLATFORMS:
            continue
        for entry in entries or []:
            targets.append(
                FeedTarget(
                    platform=platform,
                    identifier=str(entry["identifier"]),
                    company=str(entry.get("company") or entry["identifier"]),
                    base_url=str(entry.get("base_url") or ""),
                    site=str(entry.get("site") or ""),
                )
            )
    return targets


def discover_targets(known_jobs: Iterable[Dict]) -> List[FeedTarget]:
    """Derive feed coordinates from job URLs already present in the database."""
    targets: Dict[Tuple[str, str, str], FeedTarget] = {}
    for row in known_jobs:
        url = row.get("job_url") or ""
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        parts = [part for part in parsed.path.split("/") if part]
        company_data = row.get("companies") or {}
        company = company_data.get("employer_name") or row.get("company") or ""
        target = None

        if "greenhouse.io" in host and parts:
            target = FeedTarget("greenhouse", parts[0], company or parts[0])
        elif host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
            base_url = "https://api.eu.lever.co" if ".eu." in host else "https://api.lever.co"
            target = FeedTarget("lever", parts[0], company or parts[0], base_url=base_url)
        elif host == "jobs.ashbyhq.com" and parts:
            target = FeedTarget("ashby", parts[0], company or parts[0])
        elif host == "jobs.smartrecruiters.com" and parts:
            target = FeedTarget("smartrecruiters", parts[0], company or parts[0])
        elif host.endswith("myworkdayjobs.com") and parts:
            tenant = host.split(".")[0]
            site_parts = [p for p in parts if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", p)]
            site = site_parts[0] if site_parts else ""
            if site and site != "job":
                target = FeedTarget(
                    "workday", tenant, company or tenant,
                    base_url=f"{parsed.scheme}://{parsed.netloc}", site=site,
                )

        if target:
            # Historical rows can occasionally be linked to the wrong legal
            # employer. Only auto-expand a board when its slug agrees with the
            # company brand. DOL history is intentionally not required: newer
            # startups can be eligible based on their current job description.
            if _board_company_key(target.identifier) == _board_company_key(company):
                targets[target.key] = target
    return list(targets.values())


def merge_targets(*groups: Sequence[FeedTarget]) -> List[FeedTarget]:
    merged: Dict[Tuple[str, str, str], FeedTarget] = {}
    for group in groups:
        for target in group:
            merged[target.key] = target
    return sorted(merged.values(), key=lambda item: item.key)


def fetch_greenhouse(target: FeedTarget, http=requests) -> List[Dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{target.identifier}/jobs"
    response = http.get(url, params={"content": "true"}, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    jobs = []
    for item in response.json().get("jobs", []):
        location = (item.get("location") or {}).get("name", "")
        job = _normalized_job(
            title=item.get("title", ""), company=target.company,
            location=location, description=item.get("content", ""),
            job_url=item.get("absolute_url", ""), source="greenhouse_feed",
            posted_date=item.get("updated_at"), source_job_id=item.get("id", ""),
            source_board=target.identifier,
        )
        if job:
            jobs.append(job)
    return jobs


def fetch_lever(target: FeedTarget, http=requests) -> List[Dict]:
    base_url = target.base_url or "https://api.lever.co"
    endpoint = f"{base_url}/v0/postings/{target.identifier}"
    jobs = []
    skip = 0
    while True:
        response = http.get(
            endpoint,
            params={"mode": "json", "skip": skip, "limit": 100},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        page = response.json() or []
        for item in page:
            categories = item.get("categories") or {}
            description = item.get("descriptionPlain") or item.get("description") or ""
            if item.get("lists"):
                description += " " + " ".join(
                    _plain_text(block.get("content", "")) for block in item["lists"]
                )
            job = _normalized_job(
                title=item.get("text", ""), company=target.company,
                location=categories.get("location", ""), description=description,
                job_url=item.get("hostedUrl") or item.get("applyUrl", ""),
                source="lever_feed", posted_date=item.get("createdAt"),
                source_job_id=item.get("id", ""), source_board=target.identifier,
            )
            if job:
                jobs.append(job)
        if len(page) < 100 or skip + len(page) >= MAX_BOARD_LISTINGS:
            break
        skip += len(page)
    return jobs


def fetch_ashby(target: FeedTarget, http=requests) -> List[Dict]:
    endpoint = f"https://api.ashbyhq.com/posting-api/job-board/{target.identifier}"
    response = http.get(
        endpoint, params={"includeCompensation": "true"}, timeout=DEFAULT_TIMEOUT
    )
    response.raise_for_status()
    jobs = []
    for item in response.json().get("jobs", []):
        locations = [item.get("location", "")]
        locations.extend(
            location.get("location", "") for location in item.get("secondaryLocations", [])
        )
        job_url = item.get("jobUrl") or item.get("applyUrl", "")
        source_id = item.get("id") or canonicalize_job_url(job_url).rsplit("/", 1)[-1]
        job = _normalized_job(
            title=item.get("title", ""), company=target.company,
            location="; ".join(filter(None, locations)),
            description=item.get("descriptionHtml") or item.get("descriptionPlain", ""),
            job_url=job_url, source="ashby_feed",
            posted_date=item.get("publishedAt"), source_job_id=source_id,
            source_board=target.identifier,
        )
        if job and item.get("isListed", True):
            jobs.append(job)
    return jobs


def _smartrecruiters_description(item: Dict) -> str:
    sections = ((item.get("jobAd") or {}).get("sections") or {})
    return " ".join(
        section.get("text", "")
        for section in sections.values()
        if isinstance(section, dict)
    )


def fetch_smartrecruiters(target: FeedTarget, http=requests) -> List[Dict]:
    base = f"https://api.smartrecruiters.com/v1/companies/{target.identifier}/postings"
    jobs = []
    offset = 0
    while True:
        response = http.get(
            base, params={"limit": 100, "offset": offset}, timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("content", [])
        for summary in page:
            if not matches_job_level(summary.get("name", ""), "all"):
                continue
            job_id = summary.get("id", "")
            detail_response = http.get(f"{base}/{job_id}", timeout=DEFAULT_TIMEOUT)
            detail_response.raise_for_status()
            item = detail_response.json()
            location_data = item.get("location") or summary.get("location") or {}
            location = ", ".join(
                filter(None, [
                    location_data.get("city"), location_data.get("region"),
                    location_data.get("country"),
                ])
            )
            job_url = item.get("ref") or summary.get("ref")
            if not job_url:
                job_url = f"https://jobs.smartrecruiters.com/{target.identifier}/{job_id}"
            job = _normalized_job(
                title=item.get("name") or summary.get("name", ""),
                company=target.company, location=location,
                description=_smartrecruiters_description(item), job_url=job_url,
                source="smartrecruiters_feed",
                posted_date=item.get("releasedDate") or summary.get("releasedDate"),
                source_job_id=job_id, source_board=target.identifier,
            )
            if job:
                jobs.append(job)
        offset += len(page)
        total = payload.get("totalFound", len(page))
        if not page or offset >= total or offset >= MAX_BOARD_LISTINGS:
            break
    return jobs


def fetch_workday(target: FeedTarget, http=requests) -> List[Dict]:
    base_url = target.base_url.rstrip("/")
    api_root = f"{base_url}/wday/cxs/{target.identifier}/{target.site}"
    jobs = []
    offset = 0
    while True:
        response = http.post(
            f"{api_root}/jobs",
            json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("jobPostings", [])
        for summary in page:
            if not matches_job_level(summary.get("title", ""), "all"):
                continue
            external_path = summary.get("externalPath", "")
            detail_response = http.get(f"{api_root}{external_path}", timeout=DEFAULT_TIMEOUT)
            detail_response.raise_for_status()
            item = detail_response.json().get("jobPostingInfo", {})
            locations = [item.get("location") or summary.get("locationsText", "")]
            locations.extend(item.get("additionalLocations") or [])
            job = _normalized_job(
                title=item.get("title") or summary.get("title", ""),
                company=target.company, location="; ".join(filter(None, locations)),
                description=item.get("jobDescription", ""),
                job_url=f"{base_url}{external_path}", source="workday_feed",
                posted_date=_relative_workday_date(
                    item.get("postedOn") or summary.get("postedOn", "")
                ),
                source_job_id=item.get("jobReqId") or external_path.rsplit("_", 1)[-1],
                source_board=f"{target.identifier}/{target.site}",
            )
            if job:
                jobs.append(job)
        offset += len(page)
        total = payload.get("total", len(page))
        if not page or offset >= total or offset >= MAX_BOARD_LISTINGS:
            break
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workday": fetch_workday,
}


def fetch_target(target: FeedTarget, http=requests) -> List[Dict]:
    return FETCHERS[target.platform](target, http=http)


def fetch_all_targets(
    targets: Sequence[FeedTarget],
    *,
    max_workers: int = 8,
    http=requests,
) -> Tuple[List[Dict], List[str]]:
    """Fetch targets concurrently; one failed board does not discard others."""
    jobs: List[Dict] = []
    errors: List[str] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(targets) or 1))) as pool:
        futures = {pool.submit(fetch_target, target, http): target for target in targets}
        for future in as_completed(futures):
            target = futures[future]
            try:
                board_jobs = future.result()
                jobs.extend(board_jobs)
                print(f"  ✅ {target.platform}:{target.identifier} — {len(board_jobs)} jobs")
            except Exception as exc:
                message = f"{target.platform}:{target.identifier}: {exc}"
                errors.append(message)
                print(f"  ⚠️  Direct feed failed: {message}")
    return jobs, errors


def is_recent(job: Dict, lookback_days: int, now: Optional[datetime] = None) -> bool:
    """Keep unknown dates; reject only jobs known to be older than the overlap."""
    posted = _parse_datetime(job.get("posted_date"))
    if posted is None:
        return True
    now = now or datetime.now(timezone.utc)
    return posted >= now - timedelta(days=lookback_days)


def deduplicate_jobs(jobs: Iterable[Dict]) -> List[Dict]:
    """Deduplicate using ATS identity first and canonical URL second."""
    seen = set()
    unique = []
    for job in jobs:
        identity = (
            job.get("source", "").replace("_feed", ""),
            (job.get("source_board") or "").lower(),
            str(job.get("source_job_id") or ""),
        )
        key = identity if all(identity) else (canonicalize_job_url(job.get("job_url", "")),)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def select_diverse_jobs(
    jobs: Iterable[Dict], max_jobs: int, max_per_company: int = 10
) -> List[Dict]:
    """Prefer recent jobs while preventing one large board from crowding out others."""
    ordered = sorted(jobs, key=lambda job: job.get("posted_date") or "", reverse=True)
    selected = []
    company_counts: Dict[str, int] = {}
    for job in ordered:
        company = (job.get("company") or job.get("source_board") or "unknown").lower()
        if company_counts.get(company, 0) >= max_per_company:
            continue
        selected.append(job)
        company_counts[company] = company_counts.get(company, 0) + 1
        if len(selected) >= max_jobs:
            break
    return selected
