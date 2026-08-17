"""Discover and download the newest official DOL OFLC quarterly files."""
from __future__ import annotations
import argparse
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Tuple

import requests


URL_PATTERNS = {
    "perm": (
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
        "PERM_Disclosure_Data_FY{fy}_Q{quarter}.xlsx",
        "https://www.dol.gov/media/PERM_Disclosure_Data_FY{fy}_Q{quarter}.xlsx",
    ),
    "lca": (
        # DOL's current FY2026 filename contains the published typo below.
        "https://www.dol.gov/media/LCA_Dislclosure_Data_FY{fy}_Q{quarter}.xlsx",
        "https://www.dol.gov/media/LCA_Disclosure_Data_FY{fy}_Q{quarter}.xlsx",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/"
        "LCA_Disclosure_Data_FY{fy}_Q{quarter}.xlsx",
    ),
}


def current_fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year + 1 if today.month >= 10 else today.year


def candidate_releases(today: date | None = None) -> Iterable[Tuple[int, int]]:
    fiscal_year = current_fiscal_year(today)
    for year in (fiscal_year, fiscal_year - 1):
        for quarter in range(4, 0, -1):
            yield year, quarter


def find_latest_url(program: str, session: requests.Session) -> Tuple[str, int, int]:
    for fiscal_year, quarter in candidate_releases():
        for pattern in URL_PATTERNS[program]:
            url = pattern.format(fy=fiscal_year, quarter=quarter)
            try:
                response = session.head(url, allow_redirects=True, timeout=30)
                content_type = response.headers.get("content-type", "").lower()
                content_length = int(response.headers.get("content-length", "0"))
                if (
                    response.ok
                    and "spreadsheet" in content_type
                    and content_length > 10_000
                ):
                    return url, fiscal_year, quarter
            except requests.RequestException:
                continue
    raise RuntimeError(f"No current official DOL file found for {program.upper()}")


def download(url: str, destination: Path, session: requests.Session) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
    temporary.replace(destination)


def fetch_latest(output_dir: Path) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = "sponsored-jobs-rag-bot/1.0"
    downloaded = {}

    for program in ("perm", "lca"):
        url, fiscal_year, quarter = find_latest_url(program, session)
        prefix = "PERM" if program == "perm" else "LCA"
        destination = output_dir / (
            f"{prefix}_Disclosure_Data_FY{fiscal_year}_Q{quarter}.xlsx"
        )
        if not destination.exists():
            print(f"Downloading {program.upper()} FY{fiscal_year} Q{quarter}...")
            download(url, destination, session)
        else:
            print(f"Using existing {destination.name}")
        downloaded[program] = destination
        print(f"{program.upper()}: FY{fiscal_year} Q{quarter} ({url})")

    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/dol"))
    args = parser.parse_args()
    fetch_latest(args.output_dir)


if __name__ == "__main__":
    main()
