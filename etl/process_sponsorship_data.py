"""
ETL script to process H-1B, PERM, and LCA sponsorship data.
Aggregates data by employer and uploads to Supabase.
"""
import pandas as pd
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client


def normalize_employer_name(name) -> str:
    """Normalize employer name for consistent matching."""
    if pd.isna(name) or not name:
        return ""
    return str(name).strip().upper()


def process_h1b_data(file_path: Path) -> Dict[str, Dict]:
    """Process H-1B CSV data and aggregate by employer."""
    print(f"Processing H-1B data from {file_path}...")

    df = pd.read_csv(file_path)
    print(f"  Rows: {len(df)}, Columns: {list(df.columns)[:6]}")

    # Normalize employer names
    df["employer_norm"] = df["Employer"].apply(normalize_employer_name)
    df = df[df["employer_norm"] != ""]

    # Fill NaN with 0 for numeric columns
    for col in ["Initial Approval", "Initial Denial", "Continuing Approval", "Continuing Denial"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Aggregate by employer (vectorized, much faster than iterrows)
    grouped = df.groupby("employer_norm").agg({
        "Initial Approval": "sum",
        "Continuing Approval": "sum",
        "Initial Denial": "sum",
        "Continuing Denial": "sum",
        "NAICS": "first",
    }).reset_index()

    companies = {}
    for _, row in grouped.iterrows():
        employer = row["employer_norm"]
        companies[employer] = {
            "employer_name": employer,
            "naics_code": str(int(row["NAICS"])) if pd.notna(row["NAICS"]) else None,
            "h1b_approvals": int(row["Initial Approval"] + row["Continuing Approval"]),
            "h1b_denials": int(row["Initial Denial"] + row["Continuing Denial"]),
            "perm_approvals": 0,
            "perm_denials": 0,
            "lca_approvals": 0,
            "lca_denials": 0,
        }

    print(f"  Processed {len(companies)} unique companies from H-1B data")
    return companies


def process_perm_data(file_path: Path, companies: Dict[str, Dict]) -> Dict[str, Dict]:
    """Process PERM Excel data and merge with existing companies."""
    print(f"Processing PERM data from {file_path}...")

    try:
        # Only read the columns we need (much faster for 83MB file)
        df = pd.read_excel(
            file_path, engine='openpyxl',
            usecols=["EMP_BUSINESS_NAME", "CASE_STATUS"]
        )
    except Exception as e:
        print(f"  Error reading PERM Excel file: {e}")
        return companies

    print(f"  Rows: {len(df)}")

    df["employer_norm"] = df["EMP_BUSINESS_NAME"].apply(normalize_employer_name)
    df = df[df["employer_norm"] != ""]
    df["CASE_STATUS"] = df["CASE_STATUS"].fillna("").str.upper()

    # Count certified and denied per employer (vectorized)
    df["is_certified"] = df["CASE_STATUS"].str.contains("CERTIFIED", na=False).astype(int)
    df["is_denied"] = (df["CASE_STATUS"].str.contains("DENIED", na=False) |
                       df["CASE_STATUS"].str.contains("WITHDRAWN", na=False)).astype(int)

    grouped = df.groupby("employer_norm").agg(
        perm_approvals=("is_certified", "sum"),
        perm_denials=("is_denied", "sum"),
    ).reset_index()

    for _, row in grouped.iterrows():
        employer = row["employer_norm"]
        if employer in companies:
            companies[employer]["perm_approvals"] += int(row["perm_approvals"])
            companies[employer]["perm_denials"] += int(row["perm_denials"])
        else:
            companies[employer] = {
                "employer_name": employer,
                "naics_code": None,
                "h1b_approvals": 0, "h1b_denials": 0,
                "perm_approvals": int(row["perm_approvals"]),
                "perm_denials": int(row["perm_denials"]),
                "lca_approvals": 0, "lca_denials": 0,
            }

    print(f"  Total companies after PERM: {len(companies)}")
    return companies


def process_lca_data(file_path: Path, companies: Dict[str, Dict]) -> Dict[str, Dict]:
    """Process LCA Excel data and merge with existing companies."""
    print(f"Processing LCA data from {file_path}...")

    try:
        # Only read the columns we need
        df = pd.read_excel(
            file_path, engine='openpyxl',
            usecols=["EMPLOYER_NAME", "CASE_STATUS"]
        )
    except Exception as e:
        print(f"  Error reading LCA Excel file: {e}")
        return companies

    print(f"  Rows: {len(df)}")

    df["employer_norm"] = df["EMPLOYER_NAME"].apply(normalize_employer_name)
    df = df[df["employer_norm"] != ""]
    df["CASE_STATUS"] = df["CASE_STATUS"].fillna("").str.upper()

    # Count certified and denied per employer (vectorized)
    df["is_certified"] = df["CASE_STATUS"].str.contains("CERTIFIED", na=False).astype(int)
    df["is_denied"] = (df["CASE_STATUS"].str.contains("DENIED", na=False) |
                       df["CASE_STATUS"].str.contains("WITHDRAWN", na=False)).astype(int)

    grouped = df.groupby("employer_norm").agg(
        lca_approvals=("is_certified", "sum"),
        lca_denials=("is_denied", "sum"),
    ).reset_index()

    for _, row in grouped.iterrows():
        employer = row["employer_norm"]
        if employer in companies:
            companies[employer]["lca_approvals"] += int(row["lca_approvals"])
            companies[employer]["lca_denials"] += int(row["lca_denials"])
        else:
            companies[employer] = {
                "employer_name": employer,
                "naics_code": None,
                "h1b_approvals": 0, "h1b_denials": 0,
                "perm_approvals": 0, "perm_denials": 0,
                "lca_approvals": int(row["lca_approvals"]),
                "lca_denials": int(row["lca_denials"]),
            }

    print(f"  Total companies after LCA: {len(companies)}")
    return companies


def calculate_totals(companies: Dict[str, Dict]) -> Dict[str, Dict]:
    """Calculate total approvals and denials."""
    for employer, data in companies.items():
        data["total_approvals"] = (
            data["h1b_approvals"] +
            data["perm_approvals"] +
            data["lca_approvals"]
        )
        data["total_denials"] = (
            data["h1b_denials"] +
            data["perm_denials"] +
            data["lca_denials"]
        )
    return companies


def filter_quality_companies(
    companies: Dict[str, Dict],
    min_approvals: int = 3
) -> List[Dict]:
    """Filter companies with sufficient sponsorship history."""
    quality_companies = [
        data for data in companies.values()
        if data["total_approvals"] >= min_approvals
    ]

    print(f"Filtered to {len(quality_companies)} quality companies (>={min_approvals} approvals)")
    return quality_companies


def upload_to_supabase(companies: List[Dict], batch_size: int = 50) -> None:
    """Upload company data to Supabase in batches."""
    print(f"Uploading {len(companies)} companies to Supabase...")
    client = get_supabase_client()

    success_count = 0
    for i in tqdm(range(0, len(companies), batch_size), desc="Uploading batches"):
        batch = companies[i:i + batch_size]
        for company in batch:
            result = client.insert_company(company)
            if result:
                success_count += 1

    print(f"Successfully uploaded {success_count}/{len(companies)} companies")


def main():
    """Main ETL pipeline."""
    # Data files are in the parent directory of the repo
    data_dir = Path(__file__).resolve().parent.parent.parent
    h1b_file = data_dir / "h1b_datahubexport-2023.csv"
    perm_file = data_dir / "PERM_Disclosure_Data_FY2025_Q4.xlsx"
    lca_file = data_dir / "LCA_Disclosure_Data_FY2025_Q1.xlsx"

    print(f"Data directory: {data_dir}")

    # Check files exist
    if not h1b_file.exists():
        print(f"Error: H-1B file not found at {h1b_file}")
        return

    # Process data
    companies = process_h1b_data(h1b_file)

    if perm_file.exists():
        companies = process_perm_data(perm_file, companies)
    else:
        print(f"Warning: PERM file not found at {perm_file}, skipping...")

    if lca_file.exists():
        companies = process_lca_data(lca_file, companies)
    else:
        print(f"Warning: LCA file not found at {lca_file}, skipping...")

    # Calculate totals and filter
    companies = calculate_totals(companies)
    quality_companies = filter_quality_companies(companies, min_approvals=3)

    # Upload to Supabase
    upload_to_supabase(quality_companies)

    print("\n✅ ETL pipeline completed successfully!")
    print(f"Total companies processed: {len(companies)}")
    print(f"Quality companies uploaded: {len(quality_companies)}")


if __name__ == "__main__":
    main()
