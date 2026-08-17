"""Fail fast with actionable errors when an automation stage is misconfigured."""
import argparse
import os
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()


def _missing(names: Iterable[str]) -> list[str]:
    return [name for name in names if not os.getenv(name)]


def validate(stage: str) -> list[str]:
    errors = []
    database_keys = ("SUPABASE_SERVICE_KEY", "SUPABASE_KEY")

    if stage in {"database", "scrape", "match", "notify"}:
        errors.extend(_missing(["SUPABASE_URL"]))
        if not any(os.getenv(name) for name in database_keys):
            errors.append("SUPABASE_SERVICE_KEY (preferred) or SUPABASE_KEY")

    if stage == "scrape":
        has_serpapi = bool(os.getenv("SERPAPI_KEY"))
        has_google = bool(
            os.getenv("GOOGLE_SEARCH_API_KEY")
            and os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        )
        if not (has_serpapi or has_google):
            errors.append(
                "SERPAPI_KEY or both GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID"
            )
    elif stage == "match":
        errors.extend(_missing(["GROQ_API_KEY"]))
    elif stage == "notify":
        errors.extend(
            _missing(
                [
                    "SMTP_USER",
                    "SMTP_PASSWORD",
                    "NOTIFICATION_EMAIL",
                ]
            )
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["database", "scrape", "match", "notify"])
    args = parser.parse_args()
    errors = validate(args.stage)
    if errors:
        print(f"Configuration invalid for {args.stage}:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Configuration valid for {args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
