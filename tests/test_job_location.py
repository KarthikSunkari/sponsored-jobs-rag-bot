import pytest

from utils.job_location import (
    assess_sponsorship_language,
    assess_us_job_location,
    classify_sponsorship_language,
    is_us_job_eligible,
)


@pytest.mark.parametrize(
    "location",
    [
        "Hybrid - India",
        "Bengaluru, India",
        "Remote - Brazil",
        "São Paulo, Brasil",
        "LATAM",
        "Hybrid - London",
        "Toronto, Canada",
        "Ontario",
        "Indonesia",
        "China",
        "Netherlands",
        "Spain",
        "Portugal",
        "telengana, in",
        "Karnataka, IN",
    ],
)
def test_foreign_only_locations_are_excluded(location):
    eligible, reason = assess_us_job_location(location)

    assert eligible is False
    assert reason == "non-US-only location"


@pytest.mark.parametrize(
    "location",
    [
        "United States; India",
        "New York, USA / São Paulo, Brazil",
        "Remote - US, Canada, or India",
        "Global",
        "Worldwide Remote",
        "North America",
        "Headquarters/Sunnyvale Office",
    ],
)
def test_us_or_global_locations_are_retained(location):
    assert is_us_job_eligible(location) is True


def test_foreign_description_is_excluded_when_location_is_missing():
    assert is_us_job_eligible("", "This role is based in India.") is False


def test_pronoun_us_does_not_look_like_us_country_eligibility():
    description = "Join us on our global engineering team. This role is based in India."

    assert is_us_job_eligible("", description) is False


def test_foreign_location_overrides_work_from_anywhere_company_slogan():
    description = (
        "Veeva is a Work from Anywhere company, but candidates must live "
        "within commuting distance of Toronto."
    )

    assert is_us_job_eligible("Canada - Toronto", description) is False


def test_us_company_benefits_do_not_make_an_india_role_eligible():
    description = (
        "Our US-based team receives unlimited PTO. In India, employees receive "
        "statutory leave and local health coverage."
    )

    assert is_us_job_eligible("Bengaluru, India", description) is False


def test_explicit_us_description_wins_for_multi_country_role():
    description = "This position is available in the United States, India, and Brazil."

    assert is_us_job_eligible("Remote", description) is True


def test_explicit_foreign_location_wins_over_us_boilerplate():
    description = "This position supports customers throughout the United States."

    assert is_us_job_eligible("London, ON, Canada", description) is False


def test_canadian_country_code_is_not_california():
    assert is_us_job_eligible("London, ON, ca") is False


def test_foreign_country_code_is_not_us_state_code():
    assert is_us_job_eligible("Berlin, de") is False


def test_us_location_survives_alongside_canadian_country_code():
    assert is_us_job_eligible("New York, NY; Toronto, ON, CA") is True


def test_separate_us_state_location_survives_foreign_segment():
    assert is_us_job_eligible("Bengaluru, India; Redmond, WA") is True


def test_unknown_location_is_retained_conservatively():
    eligible, reason = assess_us_job_location("Headquarters Office")

    assert eligible is True
    assert reason == "location unknown or not explicitly restricted"


@pytest.mark.parametrize(
    "location", ["Berlin", "Munich", "Amsterdam", "Stockholm", "Vilnius", "Seoul"]
)
def test_foreign_city_only_locations_are_excluded(location):
    assert is_us_job_eligible(location) is False


@pytest.mark.parametrize(
    "description",
    [
        "Candidates must be authorized to work in the US without sponsorship.",
        "We will not provide visa sponsorship for this position.",
        "The company is unable to sponsor applicants.",
    ],
)
def test_explicit_no_sponsorship_language_is_excluded(description):
    eligible, reason = assess_sponsorship_language(description)

    assert eligible is False
    assert "excludes" in reason


@pytest.mark.parametrize(
    ("title", "description", "reason_fragment"),
    [
        ("Software Engineer", "U.S. citizenship is required.", "citizenship"),
        ("Software Engineer", "Applicants must be U.S. citizens.", "citizenship"),
        (
            "Software Engineer",
            "Candidates must be lawful permanent residents.",
            "permanent-resident",
        ),
        (
            "Software Engineer",
            "You must have the ability to obtain a Secret security clearance.",
            "clearance",
        ),
        ("SRE - Top Secret Clearance", "Build systems.", "clearance"),
        (
            "Software Engineer",
            "We do not consider STEM OPT candidates for this role.",
            "OPT",
        ),
        (
            "Software Engineer",
            "OPT/CPT candidates will not be considered.",
            "OPT",
        ),
        ("Software Engineer", "No visa sponsorship.", "sponsorship"),
        (
            "Software Engineer",
            "Applicants must be a U.S. person or lawful permanent resident.",
            "permanent-resident",
        ),
    ],
)
def test_incompatible_work_authorization_requirements_are_excluded(
    title, description, reason_fragment
):
    eligible, reason = assess_sponsorship_language(description, title)

    assert eligible is False
    assert reason_fragment.lower() in reason.lower()


def test_itar_enumerated_citizenship_requirement_is_excluded():
    description = (
        "ITAR REQUIREMENTS: Applicant must be a (i) U.S. citizen or national, "
        "(ii) U.S. lawful permanent resident (green card holder), (iii) refugee, "
        "or (iv) asylee, or be eligible for State Department authorization."
    )

    eligible, reason = assess_sponsorship_language(description, "Software Engineer")

    assert eligible is False
    assert "citizenship" in reason


def test_plain_us_work_authorization_is_opt_compatible():
    status, reason = classify_sponsorship_language(
        "Must be legally authorized to work in the United States."
    )

    assert status == "not_specified"
    assert "OPT" in reason


def test_explicit_sponsorship_is_identified():
    status, reason = classify_sponsorship_language(
        "H-1B sponsorship is available for qualified candidates."
    )

    assert status == "explicit_sponsorship"
    assert "explicitly" in reason
