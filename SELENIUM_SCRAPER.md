# Selenium Scraper Quick Start

## New Features

✅ **Browser-Based Scraping** - Uses Selenium to bypass Google blocking  
✅ **24-Hour Filter** - Only shows jobs posted in the last 24 hours (`tbs=qdr:d`)  
✅ **Sponsorship Integration** - Displays LCA sponsorship data for each company  
✅ **Headless Mode** - Runs without showing browser window (faster)

## Usage

### Basic Scraping (Headless)
```bash
# Scrape new grad jobs (past 24 hours)
python3 etl/scrape_jobs.py --level newgrad --max-jobs 10

# Scrape mid-level jobs (past 24 hours)
python3 etl/scrape_jobs.py --level midlevel --max-jobs 10
```

### Show Browser Window (Debug Mode)
```bash
# See what the browser is doing
python3 etl/scrape_jobs.py --level newgrad --max-jobs 5 --show-browser
```

## Sponsorship Data

Jobs from companies with LCA sponsorship history will show:
```
✅ Saved: Software Engineer II at Google [🟢 Sponsorship: 1,234 approvals, 95.2% rate]
```

### Load LCA Data (Optional)

If you have LCA/H-1B/PERM data files:

```bash
# Place files in parent directory:
# - h1b_datahubexport-2023.csv
# - PERM_Disclosure_Data_FY2025_Q4.xlsx  
# - LCA_Disclosure_Data_FY2025_Q1.xlsx

# Process and upload to Supabase
python3 etl/process_sponsorship_data.py
```

## Search Query Details

### New Grad (Past 24 Hours)
- Sites: Greenhouse, Ashby, Lever, Workday, Jobvite, SmartRecruiters, iCIMS
- Keywords: "New Grad", "University", "Entry Level", "SDE I", "Junior Software"
- Excludes: Senior, Sr, Staff, Principal, Director
- **Date Filter**: Past 24 hours only

### Mid-Level (Past 24 Hours)
- Sites: Same ATS platforms
- Keywords: "Software Engineer", "SDE II", "MTS", "Backend", "Distributed Systems"
- Excludes: Intern, Senior, Sr, Staff, Principal, Director, "New Grad"
- **Date Filter**: Past 24 hours only

## Troubleshooting

### ChromeDriver Issues
If you get ChromeDriver errors:
```bash
# Update webdriver-manager
python3 -m pip install --upgrade webdriver-manager
```

### No Results Found
- Try `--show-browser` to see what Google is showing
- Google may still be rate-limiting (wait a few minutes)
- Try reducing `--max-jobs` to 5

### Selenium Not Found
```bash
python3 -m pip install selenium==4.16.0 webdriver-manager==4.0.1
```

## Complete Workflow

```bash
# 1. Scrape jobs (past 24 hours)
python3 etl/scrape_jobs.py --level newgrad --max-jobs 10
python3 etl/scrape_jobs.py --level midlevel --max-jobs 10

# 2. Match jobs against resume
python3 rag/match_jobs.py

# 3. View top matches in terminal or Supabase dashboard
```

## Example Output

```
============================================================
Job Scraper (Selenium) - NEWGRAD
============================================================

[1/3] Searching Google for newgrad jobs (past 24 hours)...
Description: Entry-level positions for new graduates
Found 15 job URLs from Google search
Found 15 potential job URLs

[2/3] Extracting job details...
Extracting: 100%|████████████| 15/15 [00:23<00:00]
Successfully extracted 12 jobs

[3/3] Saving jobs to database...
Saving: 100%|████████████| 12/12 [00:15<00:00]
  ✅ Saved: Software Engineer - New Grad at Stripe [🟢 Sponsorship: 456 approvals, 92.3% rate]
  ✅ Saved: Associate SDE at Amazon [🟢 Sponsorship: 8,921 approvals, 88.7% rate]
  ⏭️  Job already exists: Junior Developer at Meta

============================================================
✅ Scraping completed!
Total URLs found: 15
Jobs extracted: 12
Jobs saved: 10
Duplicates skipped: 2
============================================================
```
