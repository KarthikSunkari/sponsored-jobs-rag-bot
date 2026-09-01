import pytest

from utils.job_location import (
    assess_sponsorship_language,
    assess_us_job_location,
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


def test_us_location_survives_alongside_canadian_country_code():
    assert is_us_job_eligible("New York, NY; Toronto, ON, CA") is True


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
