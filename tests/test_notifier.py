from agents.notifier import format_match_email, format_sponsorship_signal


def test_zero_dol_history_is_labeled_without_excluding_opt_candidate():
    match = {
        "title": "AI Engineer",
        "description": "Must be authorized to work in the United States.",
        "total_approvals": 0,
    }

    signal = format_sponsorship_signal(match)

    assert "no DOL sponsorship history" in signal
    assert "OPT/STEM OPT may work now" in signal
    assert "unconfirmed" in signal


def test_explicit_jd_sponsorship_takes_priority_over_missing_history():
    match = {
        "title": "Backend Engineer",
        "description": "Visa sponsorship is available for qualified candidates.",
        "total_approvals": 0,
    }

    assert format_sponsorship_signal(match).startswith(
        "JD indicates sponsorship support"
    )


def test_dol_history_is_context_not_an_eligibility_claim():
    match = {
        "title": "Software Engineer",
        "description": "Must be authorized to work in the United States.",
        "total_approvals": 12,
        "approval_rate": 75,
    }

    signal = format_sponsorship_signal(match)

    assert "DOL history: 12 approvals (75.0%)" in signal
    assert "Confirm future sponsorship" in signal


def test_email_escapes_ats_controlled_text():
    html = format_match_email(
        [
            {
                "title": "Engineer <script>alert(1)</script>",
                "employer_name": "New Startup",
                "location": "Remote - US",
                "llama_score": 80,
                "resume_profile": "SDE",
                "description": "Must be authorized to work in the US.",
                "llama_reasoning": "Good match",
                "job_url": "https://example.com/job?a=1&b=2",
                "total_approvals": 0,
            }
        ]
    )

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "a=1&amp;b=2" in html
