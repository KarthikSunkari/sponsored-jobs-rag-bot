"""
ETL script to process H-1B, PERM, and LCA sponsorship data.
Aggregates data by employer and uploads to Supabase.
"""
import pandas as pd
import hashlib
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client


def normalize_employer_name(name: str) -> str:
    """Normalize employer name for consistent matching."""
    if pd.isna(name) or not name:
        return ""
    return str(name).strip().upper()


def process_h1b_data(file_path: Path) -> Dict[str, Dict]:
    """Process H-1B CSV data and aggregate by employer."""
    print(f"Processing H-1B data from {file_path}...")
    
    df = pd.read_csv(file_path)
    companies = {}
    
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing H-1B"):
        employer = normalize_employer_name(row.get("Employer", ""))
        if not employer:
            continue
        
        if employer not in companies:
            companies[employer] = {
                "employer_name": employer,
                "naics_code": str(row.get("NAICS", "")) if pd.notna(row.get("NAICS")) else None,
                "h1b_approvals": 0,
                "h1b_denials": 0,
                "perm_approvals": 0,
                "perm_denials": 0,
                "lca_approvals": 0,
                "lca_denials": 0,
            }
        
        # Aggregate approval/denial counts
        companies[employer]["h1b_approvals"] += int(row.get("Initial Approval", 0) or 0)
        companies[employer]["h1b_approvals"] += int(row.get("Continuing Approval", 0) or 0)
        companies[employer]["h1b_denials"] += int(row.get("Initial Denial", 0) or 0)
        companies[employer]["h1b_denials"] += int(row.get("Continuing Denial", 0) or 0)
    
    print(f"Processed {len(companies)} unique companies from H-1B data")
    return companies


def process_perm_data(file_path: Path, companies: Dict[str, Dict]) -> Dict[str, Dict]:
    """Process PERM Excel data and merge with existing companies."""
    print(f"Processing PERM data from {file_path}...")
    
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
    except Exception as e:
        print(f"Error reading PERM Excel file: {e}")
        return companies
    
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing PERM"):
        employer = normalize_employer_name(row.get("Employer Name", ""))
        if not employer:
            continue
        
        if employer not in companies:
            companies[employer] = {
                "employer_name": employer,
                "naics_code": None,
                "h1b_approvals": 0,
                "h1b_denials": 0,
                "perm_approvals": 0,
                "perm_denials": 0,
                "lca_approvals": 0,
                "lca_denials": 0,
            }
        
        # PERM data structure (adjust based on actual columns)
        status = str(row.get("Case Status", "")).upper()
        if "CERTIFIED" in status:
            companies[employer]["perm_approvals"] += 1
        elif "DENIED" in status or "WITHDRAWN" in status:
            companies[employer]["perm_denials"] += 1
    
    print(f"Total companies after PERM: {len(companies)}")
    return companies


def process_lca_data(file_path: Path, companies: Dict[str, Dict]) -> Dict[str, Dict]:
    """Process LCA Excel data and merge with existing companies."""
    print(f"Processing LCA data from {file_path}...")
    
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
    except Exception as e:
        print(f"Error reading LCA Excel file: {e}")
        return companies
    
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Processing LCA"):
        employer = normalize_employer_name(row.get("Employer Name", ""))
        if not employer:
            continue
        
        if employer not in companies:
            companies[employer] = {
                "employer_name": employer,
                "naics_code": None,
                "h1b_approvals": 0,
                "h1b_denials": 0,
                "perm_approvals": 0,
                "perm_denials": 0,
                "lca_approvals": 0,
                "lca_denials": 0,
            }
        
        # LCA data structure (adjust based on actual columns)
        status = str(row.get("Case Status", "")).upper()
        if "CERTIFIED" in status:
            companies[employer]["lca_approvals"] += 1
        elif "DENIED" in status or "WITHDRAWN" in status:
            companies[employer]["lca_denials"] += 1
    
    print(f"Total companies after LCA: {len(companies)}")
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
    quality_companies = []
    
    for employer, data in companies.items():
        if data["total_approvals"] >= min_approvals:
            quality_companies.append(data)
    
    print(f"Filtered to {len(quality_companies)} quality companies (>={min_approvals} approvals)")
    return quality_companies


def upload_to_supabase(companies: List[Dict]) -> None:
    """Upload company data to Supabase."""
    print("Uploading to Supabase...")
    client = get_supabase_client()
    
    success_count = 0
    for company in tqdm(companies, desc="Uploading"):
        result = client.insert_company(company)
        if result:
            success_count += 1
    
    print(f"Successfully uploaded {success_count}/{len(companies)} companies")


def main():
    """Main ETL pipeline."""
    # Define data paths
    data_dir = Path(__file__).parent.parent.parent / "Jobs Bot"
    h1b_file = data_dir / "h1b_datahubexport-2023.csv"
    perm_file = data_dir / "PERM_Disclosure_Data_FY2025_Q4.xlsx"
    lca_file = data_dir / "LCA_Disclosure_Data_FY2025_Q1.xlsx"
    
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
