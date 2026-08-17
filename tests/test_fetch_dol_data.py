from datetime import date

from etl.fetch_dol_data import candidate_releases, current_fiscal_year


def test_fiscal_year_rolls_over_in_october():
    assert current_fiscal_year(date(2026, 9, 30)) == 2026
    assert current_fiscal_year(date(2026, 10, 1)) == 2027


def test_candidates_prefer_newest_quarter_and_fallback_year():
    candidates = list(candidate_releases(date(2026, 8, 16)))
    assert candidates[:4] == [(2026, 4), (2026, 3), (2026, 2), (2026, 1)]
    assert candidates[-1] == (2025, 1)
