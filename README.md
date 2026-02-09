# Intelligent Sponsored Jobs Search Agent

MCP-based job search system using LangChain and Groq's Llama-3.1-8B-Instant for semantic job matching against resume embeddings. Leverages DOL H-1B/PERM/LCA data to filter companies by visa sponsorship history.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GITHUB ACTIONS (Scheduler)                  │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │ Daily 9 AM   │      │ Daily 6 PM   │      │  On-demand   │  │
│  │ Scrape Jobs  │      │ Match & Rank │      │  Manual Run  │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │                       │                      │
           ▼                       ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MCP SERVER (FastMCP)                     │
│  Tools Exposed:                                                 │
│  • search_jobs(query, location, sponsorship_filter)             │
│  • ingest_job_posting(url, company_name, title)                 │
│  • match_resume(job_ids, resume_embedding)                      │
│  • score_relevance(job_id, resume_text) → 0-100                 │
└─────────────────────────────────────────────────────────────────┘
           │                       │
           ▼                       ▼
┌──────────────────┐    ┌──────────────────────────────────┐
│  SerpAPI Google  │    │  Supabase (pgvector)             │
│  Search          │    │  • companies (15K+ H1B sponsors) │
│  • LinkedIn Jobs │    │  • jobs (embeddings)             │
│  • Indeed        │    │  • user_resume (embedding)       │
│  • Glassdoor     │    │  • job_matches (scores)          │
└──────────────────┘    └──────────────────────────────────┘
           │                       │
           └───────────┬───────────┘
                       ▼
           ┌───────────────────────┐
           │  LangChain Agent       │
           │  (Groq Llama-3.1-8B)   │
           │  • Orchestrates tools  │
           │  • Scores relevance    │
           │  • Generates summaries │
           └───────────────────────┘
                       │
                       ▼
           ┌───────────────────────┐
           │  Email Notifier        │
           │  • Top 10 matches/day  │
           │  • >80% relevance only │
           │  • Gmail SMTP          │
           └───────────────────────┘
```

## Features

- **Zero-Cost Architecture** - Groq API (30 req/min) + GitHub Actions (2,000 min/month) + Supabase free tier
- **Sub-Second Inference** - Groq's Llama-3.1-8B-Instant for job relevance scoring
- **MCP Server** - Standardized tool interfaces for agent orchestration
- **Semantic Search** - pgvector with 384-dimensional embeddings (all-MiniLM-L6-v2)
- **Sponsorship Filtering** - DOL H-1B/PERM/LCA data (15,000+ companies, >70% approval rate)
- **Automated Workflow** - GitHub Actions cron jobs for daily scraping and matching
- **Smart Notifications** - Email digest with top matches (>80% relevance threshold)

## Setup

### 1. Prerequisites

- Python 3.11+
- Supabase account (free tier)
- Groq API key (free tier: 30 req/min)
- GitHub account (for Actions)

### 2. Install Dependencies

```bash
cd sponsored-jobs-rag-bot
pip install -r requirements.txt
```

### 3. Get Groq API Key

1. Sign up at [console.groq.com](https://console.groq.com)
2. Create a new API key (free tier: 30 requests/min)
3. Copy the key for next step

### 4. Configure Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to SQL Editor and run `supabase/schema.sql`
3. Enable pgvector extension:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
4. Copy your project URL and API keys

### 5. Environment Variables

```bash
cp .env.example .env
# Edit .env with:
# - Supabase URL and keys
# - Groq API key
# - GitHub token (for Actions)
```

### 6. Process Sponsorship Data

```bash
# Process H-1B, PERM, and LCA data and upload to Supabase
python etl/process_sponsorship_data.py
```

Expected output:
```
Processing H-1B data...
Processed 33,334 unique companies from H-1B data
Processing PERM data...
Processing LCA data...
Filtered to 15,000+ quality companies (>=3 approvals)
Successfully uploaded to Supabase
```

### 7. Upload Your Resume

```python
from utils.supabase_client import get_supabase_client

client = get_supabase_client()
client.client.table("user_resume").insert({
    "resume_text": "Your resume text here...",
    "skills": ["Python", "Machine Learning", "etc"],
    "experience_years": 5
}).execute()
```

### 8. Configure GitHub Actions

1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Add secrets:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SUPABASE_SERVICE_KEY`
   - `GROQ_API_KEY`
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `NOTIFICATION_EMAIL`
3. Workflows will run automatically (daily at 9 AM and 6 PM EST)

### 9. Test the System

```bash
# Test Groq API connection
python agents/groq_client.py

# Test MCP server
python agents/mcp_server.py

# Test LangChain agent
python agents/langchain_agent.py

# Run job matching manually
python rag/match_jobs.py
```

## Usage

### Daily Workflow (Automated)

1. **GitHub Actions scrapes jobs** (9 AM EST)
   - Fetches from LinkedIn, Indeed, Glassdoor via SerpAPI
   - Filters by sponsorship companies (DOL LCA data)
   - Stores in Supabase
   - Generates embeddings automatically

2. **GitHub Actions matches jobs** (6 PM EST)
   - Retrieves new jobs from Supabase
   - Performs vector similarity search (pgvector)
   - Scores top matches with Groq Llama-3
   - Sends email notification with top matches

3. **Manual trigger** (optional)
   ```bash
   # Trigger workflows manually from GitHub Actions tab
   # Or run locally:
   python rag/match_jobs.py
   python agents/notifier.py
   ```

### Manual Commands

```bash
# Process new sponsorship data (DOL LCA)
python etl/process_sponsorship_data.py

# Test Groq API connection
python agents/groq_client.py

# Test MCP server
python agents/mcp_server.py

# Test LangChain agent
python agents/langchain_agent.py

# Match jobs against resume (uses Groq)
python rag/match_jobs.py

# Send daily digest
python agents/notifier.py
```

## Database Schema

- **companies** - Sponsorship history (H-1B, PERM, LCA)
- **jobs** - Scraped job listings
- **job_embeddings** - Vector embeddings (384-dim)
- **user_resume** - Your resume + embedding
- **job_matches** - Scored matches (cosine + Llama)
- **applications** - Application tracking

## Configuration

Edit `.env` to customize:

```bash
# Matching thresholds
MIN_RELEVANCE_SCORE=80  # Only notify for scores >= 80
MAX_DAILY_MATCHES=20    # Top N jobs to score with Llama

# Scraping
SCRAPE_INTERVAL_HOURS=24
MIN_JOBS_PER_DAY=50
```

## Implemented Features

- **Serverless Architecture** - Zero infrastructure management
- **MCP-Based Orchestration** - Standardized tool interfaces
- **Sub-Second Inference** - Groq API (<1s per job)
- **Cloud-Native RAG** - Supabase pgvector for semantic search
- **Multi-Source Scraping** - GitHub Actions automation
- **Sponsorship Filtering** - DOL LCA data (>70% approval rate)
- **Smart Notifications** - Daily digest (>80% relevance)
- **Application Tracking** - Deduplication and tracking

## Future Enhancements

- AI cover letter generation
- Company research agent (Glassdoor scraping)
- Skill gap analysis
- Auto-apply bot (Playwright)
- Salary negotiation agent
- Interview prep generator

## Troubleshooting

**Groq API errors:**
- Verify API key in GitHub Secrets
- Check rate limits (30 req/min on free tier)
- Test locally: `python agents/groq_client.py`

**Supabase connection error:**
- Check `.env` credentials
- Verify pgvector extension is enabled

**GitHub Actions not running:**
- Check workflow permissions in repo settings
- Verify all secrets are configured
- Check Actions tab for error logs

**No jobs found:**
- Trigger scraping workflow manually
- Check Supabase `jobs` table
- Verify sponsorship data is loaded

## Cost Breakdown

| Component | Free Tier Limits | Cost |
|-----------|------------------|------|
| Groq API | 30 req/min, 14,400 req/day | $0 |
| GitHub Actions | 2,000 minutes/month | $0 |
| Supabase | 500MB DB + pgvector | $0 |
| Embeddings (sentence-transformers) | Unlimited (local) | $0 |
| **Total** | **Plenty for daily use** | **$0/month** |

## License

MIT

## Contributing

PRs welcome. Focus areas:
- Additional job board integrations
- Improved Llama prompts
- Better email templates
- Application tracking UI
