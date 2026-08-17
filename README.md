# sponsored-jobs-rag-bot

Automated job discovery pipeline that scrapes ATS platforms daily, scores listings against your resume using a two-stage RAG pipeline (pgvector + a Groq-hosted model), and cross-references each employer against 18K+ companies from DOL H-1B/PERM/LCA filings to surface visa sponsorship likelihood. Runs on free-tier infrastructure at modest daily volume.

## How it works

```
 GitHub Actions (cron: 9 AM EST daily)
 ├─ scrape-newgrad-jobs ──┐
 ├─ scrape-midlevel-jobs ─┤
 │                        ▼
 │                   match-jobs ──► send-notifications
 │
 └─ Pipeline per job:
     1. SerpAPI → ATS URLs (Greenhouse, Lever, Ashby, Workday, SmartRecruiters)
     2. Platform-specific extraction (JSON APIs where available, HTML fallback)
     3. Embed job text → 384-dim vector (all-MiniLM-L6-v2)
     4. Store in Supabase (pgvector)
     5. Cosine similarity vs. resume embedding → top 50 candidates
     6. Groq GPT-OSS 20B rescoring → top 20 with reasoning
     7. Fuzzy-match employer → DOL sponsorship data (approval rate, history)
     8. Email digest: ranked matches with scores + sponsorship stats
```

## Architecture

```
etl/
├── scrape_jobs.py              # 3-tier search: SerpAPI → Google CSE → Selenium
├── process_sponsorship_data.py # DOL H-1B/PERM/LCA ETL → companies table
└── search_queries.yaml         # Site-scoped Google dorks per experience level

rag/
├── embedding_service.py        # sentence-transformers wrapper (MiniLM-L6-v2)
├── match_jobs.py               # Vector search + LLM rescoring pipeline
└── llama_scorer.py             # Local scorer (deprecated, replaced by Groq)

agents/
├── groq_client.py              # Groq API client w/ retry + JSON mode
├── langchain_agent.py          # Experimental agent (not used by daily workflow)
├── mcp_server.py               # Experimental tool facade
└── notifier.py                 # SMTP email digest

utils/
├── supabase_client.py          # DB client singleton
├── serpapi_client.py            # SerpAPI wrapper
├── google_search.py            # Google Custom Search fallback
└── resume_extractor.py         # Resume text extraction

supabase/
├── schema.sql                  # 6 tables + indexes + views
└── rpc_functions.sql           # pgvector match_jobs() RPC
```

## Data flow

**Scraping** — `etl/scrape_jobs.py` reads `search_queries.yaml` for site-scoped Google dorks targeting 7 ATS platforms. Extraction is platform-aware:

| Platform | Method | Why |
|----------|--------|-----|
| Greenhouse | REST API (`boards-api.greenhouse.io/v1/boards/{co}/jobs/{id}`) | HTML is JS-rendered |
| Ashby | GraphQL API (`jobs.ashbyhq.com/api/non-user-graphql`) | HTML is JS-rendered |
| Lever | HTML scraping (`div.posting-headline`, `div.section-wrapper`) | Server-rendered |
| SmartRecruiters | `<title>` tag + meta extraction | Partial SSR |
| Workday, iCIMS, Jobvite | Generic HTML fallback | Varies |

**Matching** — `rag/match_jobs.py` runs a two-stage retrieval pipeline:
1. **Recall**: cosine similarity (pgvector IVFFlat index) between resume and job embeddings → top 50
2. **Precision**: Groq GPT-OSS 20B scores each job 0-100 with structured JSON output (`response_format: json_object`) → top 20

**Sponsorship** — `etl/process_sponsorship_data.py` ingests three DOL datasets:
- H-1B Employer Data Hub (CSV) — initial/continuing approvals & denials by employer
- PERM Disclosure Data (Excel, ~83MB) — certified/denied/withdrawn cases
- LCA Disclosure Data (Excel) — certified/denied cases

Aggregated into a `companies` table (18,385 employers with >= 3 total approvals). Jobs are fuzzy-matched to DOL employers via `ILIKE` prefix search, preferring the entry with the highest approval count.

## Database schema

```sql
companies    -- 18K+ employers: h1b/perm/lca approvals & denials, approval_rate
jobs         -- scraped listings: title, description, location, url_hash (dedup)
job_embeddings -- vector(384) per job, IVFFlat cosine index
user_resume  -- resume text + embedding
job_matches  -- cosine_similarity, llama_score, reasoning, is_notified
applications -- tracking (applied, interview, offer, rejected)
```

`match_jobs()` RPC handles vector similarity search server-side when the dataset is large enough to warrant it.

## Setup

### Prerequisites

- Python 3.11+
- [Supabase](https://supabase.com) project (free tier)
- [Groq](https://console.groq.com) API key
- [SerpAPI](https://serpapi.com) key (250 searches/month free as of August 2026)

### Install

```bash
git clone https://github.com/KarthikSunkari/sponsored-jobs-rag-bot.git
cd sponsored-jobs-rag-bot
pip install -r requirements.txt
```

### Database

Run both SQL files in Supabase SQL Editor (Settings → SQL Editor):

```bash
supabase/schema.sql          # tables, indexes, views, triggers
supabase/rpc_functions.sql   # match_jobs() vector search RPC
supabase/migrate_match_dedup.sql # existing databases only: deduplicate matches
```

### Environment

```bash
cp .env.example .env
```

Required variables:

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
GROQ_API_KEY=gsk_...
SERPAPI_KEY=...
```

Optional (for email notifications):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail app password
NOTIFICATION_EMAIL=you@gmail.com
```

### Load sponsorship data

Download DOL datasets and place them in the parent directory:

```bash
# Expected files (parent of repo root):
../h1b_datahubexport-2023.csv
../PERM_Disclosure_Data_FY2025_Q4.xlsx
../LCA_Disclosure_Data_FY2025_Q1.xlsx

python etl/process_sponsorship_data.py
# → 73,975 total employers processed
# → 18,385 quality employers uploaded (>= 3 approvals)
```

To discover and ingest the newest cumulative OFLC quarterly PERM/LCA files:

```bash
python etl/fetch_dol_data.py --output-dir ../dol-data
python etl/process_sponsorship_data.py \
  --data-dir ../dol-data \
  --preserve-existing-h1b
```

The `Quarterly DOL Sponsorship Refresh` workflow runs in February, May,
August, and November and can also be triggered manually.

### Upload resume

```python
from utils.supabase_client import get_supabase_client

client = get_supabase_client()
client.client.table("user_resume").insert({
    "resume_text": "Your full resume text...",
    "skills": ["Python", "Distributed Systems", "AWS"],
    "experience_years": 3
}).execute()
```

Multiple named profiles are supported. Upload a plain-text resume and choose
which roles it targets:

```bash
python utils/resume_extractor.py \
  --profile "Agentic AI" \
  --resume-file agentic-ai-resume.txt \
  --target-role "AI Engineer" \
  --target-role "Agentic AI Engineer"

# Match all active profiles, or only one profile:
python rag/match_jobs.py
python rag/match_jobs.py --profile "Agentic AI"
```

### GitHub Actions secrets

Go to repo Settings → Secrets and variables → Actions. Add:

| Secret | Required |
|--------|----------|
| `SUPABASE_URL` | Yes |
| `SUPABASE_KEY` | Yes |
| `SUPABASE_SERVICE_KEY` | Yes |
| `GROQ_API_KEY` | Yes |
| `SERPAPI_KEY` | Yes |
| `GOOGLE_SEARCH_API_KEY` | For Tier 2 fallback |
| `GOOGLE_SEARCH_ENGINE_ID` | For Tier 2 fallback |
| `SMTP_HOST` | For notifications |
| `SMTP_PORT` | For notifications |
| `SMTP_USER` | For notifications |
| `SMTP_PASSWORD` | For notifications |
| `NOTIFICATION_EMAIL` | For notifications |

## Usage

### Automated (GitHub Actions)

The `daily-jobs.yml` workflow runs at 9 AM EST:

1. **scrape-newgrad-jobs** — scrapes up to 25 new grad listings (parallel)
2. **scrape-midlevel-jobs** — scrapes up to 25 mid-level listings (parallel)
3. **match-jobs** — vector search + LLM scoring against resume (sequential)
4. **send-notifications** — email digest of matches scoring >= 80 (sequential)

Trigger manually from the Actions tab or via CLI:

```bash
gh workflow run "Daily Job Scraping and Matching"
```

### Local

```bash
# Scrape jobs
python etl/scrape_jobs.py --level newgrad --max-jobs 25
python etl/scrape_jobs.py --level midlevel --max-jobs 25

# Match against resume
python rag/match_jobs.py

# Send email digest
python agents/notifier.py

# Test Groq connection
python agents/groq_client.py

# Test MCP server
python agents/mcp_server.py
```

## Cost

| Service | Free tier | Bottleneck |
|---------|-----------|------------|
| Groq | Account/model-specific | LLM scoring (2s sleep between calls) |
| GitHub Actions | 2,000 min/month | ~5 min/run × 30 days = 150 min |
| Supabase | 500MB DB, pgvector | 18K companies + jobs fits comfortably |
| SerpAPI | 250 searches/month | 2 searches/day × 30 = 60 |
| sentence-transformers | Local, unlimited | ~3s model load, <50ms/embedding |
| **Total** | | **$0/month** |

## Troubleshooting

**Supabase 521 error** — Free-tier projects pause after 7 days of inactivity. Restore from the Supabase dashboard.

**Groq rate limit errors** — The pipeline sleeps 2s between scoring calls. If you're hitting limits, reduce `max_jobs` in the scraper or `MAX_DAILY_MATCHES` in the workflow.

**0% approval rate on all jobs** — Sponsorship data hasn't been loaded. Run `python etl/process_sponsorship_data.py`. The fuzzy matcher requires company names in the `companies` table to link against.

**No jobs extracted** — Some ATS platforms (Workday, iCIMS) are fully JS-rendered and may return empty descriptions. Greenhouse and Ashby use API-based extraction and are the most reliable.

**GitHub Actions failing** — Check that all required secrets are configured. The workflow does not install Chrome/Selenium — extraction is API-based.

## License

MIT
