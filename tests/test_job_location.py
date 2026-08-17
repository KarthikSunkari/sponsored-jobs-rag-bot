import pytest

from utils.job_location import assess_us_job_location, is_us_job_eligible


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


def test_unknown_location_is_retained_conservatively():
    eligible, reason = assess_us_job_location("Headquarters Office")

    assert eligible is True
    assert reason == "location unknown or not explicitly restricted"
