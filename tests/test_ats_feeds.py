from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from etl.ats_feeds import (
    FeedTarget,
    canonicalize_job_url,
    deduplicate_jobs,
    discover_targets,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    fetch_smartrecruiters,
    fetch_workday,
    is_recent,
    matches_job_level,
    select_diverse_jobs,
)
from etl.scrape_jobs import _extract_html_generic


def response(payload):
    result = MagicMock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


def test_canonical_url_removes_tracking_and_apply_variant():
    url = "https://jobs.lever.co/acme/abc-123/apply?lever-source=test#form"

    assert canonicalize_job_url(url) == "https://jobs.lever.co/acme/abc-123"


def test_targets_are_discovered_from_existing_job_urls():
    known_jobs = [
        {
            "job_url": "https://boards.greenhouse.io/acme/jobs/123",
            "companies": {"employer_name": "Acme Inc", "total_approvals": 5},
        },
        {
            "job_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/x_JR1",
            "companies": {"employer_name": "NVIDIA", "total_approvals": 5},
        },
    ]

    targets = discover_targets(known_jobs)

    assert FeedTarget("greenhouse", "acme", "Acme Inc") in targets
    assert FeedTarget(
        "workday",
        "nvidia",
        "NVIDIA",
        "https://nvidia.wd5.myworkdayjobs.com",
        "NVIDIAExternalCareerSite",
    ) in targets


def test_zero_approval_companies_do_not_expand_dynamic_boards():
    targets = discover_targets(
        [
            {
                "job_url": "https://jobs.ashbyhq.com/aggregator/job-1",
                "companies": {"employer_name": "Aggregator", "total_approvals": 0},
            }
        ]
    )

    assert targets == []


def test_dynamic_board_slug_must_match_sponsor_brand():
    targets = discover_targets(
        [
            {
                "job_url": "https://jobs.ashbyhq.com/applied/job-1",
                "companies": {
                    "employer_name": "Applied Materials, Inc",
                    "total_approvals": 50,
                },
            },
            {
                "job_url": "https://jobs.ashbyhq.com/neara/job-2",
                "companies": {
                    "employer_name": "Neara Software Inc",
                    "total_approvals": 5,
                },
            },
        ]
    )

    assert FeedTarget("ashby", "applied", "Applied Materials, Inc") not in targets
    assert FeedTarget("ashby", "neara", "Neara Software Inc") in targets


def test_greenhouse_feed_normalizes_public_jobs():
    http = MagicMock()
    http.get.return_value = response(
        {
            "jobs": [
                {
                    "id": 123,
                    "title": "Software Engineer II",
                    "location": {"name": "New York, NY"},
                    "content": "<p>Build APIs</p>",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/123?gh_src=x",
                    "updated_at": "2026-08-30T12:00:00Z",
                }
            ]
        }
    )

    jobs = fetch_greenhouse(FeedTarget("greenhouse", "acme", "Acme"), http=http)

    assert jobs[0]["description"] == "Build APIs"
    assert jobs[0]["job_url"] == "https://boards.greenhouse.io/acme/jobs/123"
    assert jobs[0]["posted_date"] == "2026-08-30T12:00:00+00:00"


def test_lever_feed_normalizes_lists_and_millisecond_date():
    http = MagicMock()
    http.get.return_value = response(
        [
            {
                "id": "lever-1",
                "text": "Backend Software Engineer",
                "categories": {"location": "Austin, TX"},
                "descriptionPlain": "Build services.",
                "lists": [{"content": "<b>Python</b>"}],
                "hostedUrl": "https://jobs.lever.co/acme/lever-1",
                "createdAt": 1788091200000,
            }
        ]
    )

    jobs = fetch_lever(FeedTarget("lever", "acme", "Acme"), http=http)

    assert jobs[0]["source_job_id"] == "lever-1"
    assert "Python" in jobs[0]["description"]
    assert jobs[0]["posted_date"].startswith("2026-")


def test_ashby_feed_preserves_secondary_locations():
    http = MagicMock()
    http.get.return_value = response(
        {
            "jobs": [
                {
                    "id": "ashby-1",
                    "title": "AI Engineer",
                    "location": "New York, NY",
                    "secondaryLocations": [{"location": "Remote - US"}],
                    "descriptionHtml": "<p>Agents</p>",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/ashby-1",
                    "publishedAt": "2026-08-30T10:00:00Z",
                    "isListed": True,
                }
            ]
        }
    )

    jobs = fetch_ashby(FeedTarget("ashby", "acme", "Acme"), http=http)

    assert jobs[0]["location"] == "New York, NY; Remote - US"


def test_smartrecruiters_fetches_details_only_for_relevant_titles():
    http = MagicMock()
    http.get.side_effect = [
        response(
            {
                "totalFound": 2,
                "content": [
                    {"id": "1", "name": "Software Engineer II"},
                    {"id": "2", "name": "Accountant"},
                ],
            }
        ),
        response(
            {
                "id": "1",
                "name": "Software Engineer II",
                "location": {"city": "Austin", "region": "TX", "country": "US"},
                "ref": "https://jobs.smartrecruiters.com/Acme/1-software-engineer",
                "releasedDate": "2026-08-30T10:00:00Z",
                "jobAd": {"sections": {"jobDescription": {"text": "Build APIs"}}},
            }
        ),
    ]

    jobs = fetch_smartrecruiters(
        FeedTarget("smartrecruiters", "Acme", "Acme"), http=http
    )

    assert [job["title"] for job in jobs] == ["Software Engineer II"]
    assert http.get.call_count == 2


def test_workday_uses_cxs_list_and_detail_endpoints():
    http = MagicMock()
    http.post.return_value = response(
        {
            "total": 2,
            "jobPostings": [
                {
                    "title": "Platform Software Engineer",
                    "externalPath": "/job/Austin/Platform-Software-Engineer_R1",
                    "locationsText": "US, TX, Austin",
                    "postedOn": "Posted 2 Days Ago",
                },
                {"title": "Accountant", "externalPath": "/job/Austin/Accountant_R2"},
            ],
        }
    )
    http.get.return_value = response(
        {
            "jobPostingInfo": {
                "title": "Platform Software Engineer",
                "location": "US, TX, Austin",
                "additionalLocations": ["US, Remote"],
                "jobDescription": "<p>Build a cloud platform</p>",
                "postedOn": "Posted 2 Days Ago",
                "jobReqId": "R1",
            }
        }
    )
    target = FeedTarget(
        "workday", "acme", "Acme", "https://acme.wd1.myworkdayjobs.com", "jobs"
    )

    jobs = fetch_workday(target, http=http)

    assert [job["source_job_id"] for job in jobs] == ["R1"]
    assert jobs[0]["location"] == "US, TX, Austin; US, Remote"
    assert http.get.call_count == 1


def test_level_filter_rejects_upper_level_and_non_engineering_titles():
    assert matches_job_level("Software Engineer II")
    assert matches_job_level("Junior Software Engineer", "newgrad")
    assert not matches_job_level("Senior Software Engineer")
    assert not matches_job_level("Product Manager")


def test_recent_filter_keeps_unknown_dates_and_rejects_stale_jobs():
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)

    assert is_recent({"posted_date": None}, 7, now=now)
    assert is_recent({"posted_date": (now - timedelta(days=6)).isoformat()}, 7, now=now)
    assert not is_recent({"posted_date": (now - timedelta(days=8)).isoformat()}, 7, now=now)


def test_deduplication_prefers_ats_identity_over_tracking_variants():
    first = {
        "source": "ashby_feed",
        "source_board": "acme",
        "source_job_id": "job-1",
        "job_url": "https://jobs.ashbyhq.com/acme/job-1",
    }
    duplicate = {**first, "job_url": first["job_url"] + "?utm_source=test"}

    assert deduplicate_jobs([first, duplicate]) == [first]


def test_diverse_selection_caps_each_company():
    jobs = [
        {"company": "Acme", "title": f"Engineer {i}", "posted_date": f"2026-08-{30-i:02d}"}
        for i in range(3)
    ] + [
        {"company": "Beta", "title": "Engineer", "posted_date": "2026-08-27"}
    ]

    selected = select_diverse_jobs(jobs, max_jobs=4, max_per_company=2)

    assert sum(job["company"] == "Acme" for job in selected) == 2
    assert any(job["company"] == "Beta" for job in selected)


def test_generic_extractor_prefers_schema_org_job_posting():
    html = b"""
    <html><script type="application/ld+json">
    {"@type":"JobPosting","title":"Software Engineer II",
     "description":"<p>Build APIs</p>","datePosted":"2026-08-30",
     "hiringOrganization":{"name":"Acme"},
     "jobLocation":{"address":{"addressLocality":"Austin",
     "addressRegion":"TX","addressCountry":"US"}}}
    </script></html>
    """
    fake_response = MagicMock(content=html)
    fake_response.raise_for_status.return_value = None

    with patch("etl.scrape_jobs.requests.get", return_value=fake_response):
        job = _extract_html_generic("https://careers.acme.com/job/1")

    assert job["company"] == "Acme"
    assert job["location"] == "Austin, TX, US"
    assert job["description"] == "Build APIs"
