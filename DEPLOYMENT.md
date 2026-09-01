# Docker + GitHub Actions Deployment Guide

## Overview

This system uses Docker containerization for consistent Selenium execution across local and GitHub Actions environments.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│             GitHub Actions (Daily at 14:00 UTC)         │
├─────────────────────────────────────────────────────────┤
│  1. Poll direct ATS feeds + discovery (100 jobs)        │
│  2. Match Jobs (pgvector + Groq)                        │
│  3. Send Email Notifications (score >= 60)              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                      │
│  - Python 3.11                                          │
│  - Chrome (headless)                                    │
│  - ChromeDriver (auto-managed)                          │
│  - All Python dependencies                              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                  Supabase (pgvector)                    │
│  - Jobs storage                                         │
│  - Embeddings (384-dim)                                 │
│  - Match results                                        │
└─────────────────────────────────────────────────────────┘
```

## Local Testing with Docker

### Build and Run
```bash
# Build Docker image
docker build -t jobs-scraper .

# Run scraper (new grad)
docker run --env-file .env jobs-scraper python etl/scrape_jobs.py --level newgrad --max-jobs 10

# Run scraper (mid-level)
docker run --env-file .env jobs-scraper python etl/scrape_jobs.py --level midlevel --max-jobs 10

# Run matching pipeline
docker run --env-file .env jobs-scraper python rag/match_jobs.py
```

### Using Docker Compose (Recommended)
```bash
# Run complete pipeline (scrape → match → notify)
docker-compose up

# Run specific service
docker-compose up scraper
docker-compose up matcher
docker-compose up notifier

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f scraper
docker-compose logs -f matcher

# Stop all services
docker-compose down
```

## GitHub Actions Setup

### 1. Configure Secrets

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add the following secrets:

| Secret Name | Value | Example |
|-------------|-------|---------|
| `SUPABASE_URL` | Your Supabase project URL | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Supabase anon/public key | `eyJhbGc...` |
| `SUPABASE_SERVICE_KEY` | Supabase service_role key | `eyJhbGc...` |
| `GROQ_API_KEY` | Groq API key | `gsk_...` |
| `SMTP_HOST` | Email SMTP host | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | Your email | `sanji14916@gmail.com` |
| `SMTP_PASSWORD` | Gmail app password | `xxxx xxxx xxxx xxxx` |
| `NOTIFICATION_EMAIL` | Notification recipient | `sanji14916@gmail.com` |

### 2. Enable GitHub Actions

1. Go to **Actions** tab in your repo
2. Enable workflows if prompted
3. The workflow will run automatically at 9 AM EST daily
4. You can also trigger manually via **Run workflow** button

### 3. Monitor Runs

- Go to **Actions** tab to see workflow runs
- Click on a run to see detailed logs
- Download artifacts (logs) for debugging

## Workflow Schedule

The GitHub Actions workflow runs:
- **Daily at 9 AM EST** (2 PM UTC)
- **Manual trigger** available anytime

## Cost Analysis

| Component | Usage | Cost |
|-----------|-------|------|
| GitHub Actions | ~15 min/day | **$0** (2,000 min/month free) |
| Groq API | ~50 requests/day | **$0** (30 req/min free) |
| Supabase | Storage + queries | **$0** (500MB free) |
| **Total** | | **$0/month** |

## Customization

### Change Schedule
Edit `.github/workflows/daily-jobs.yml`:
```yaml
schedule:
  # Run at 6 AM EST (11 AM UTC)
  - cron: '0 11 * * *'
  
  # Run twice daily (9 AM and 6 PM EST)
  - cron: '0 14 * * *'  # 9 AM EST
  - cron: '0 23 * * *'  # 6 PM EST
```

### Adjust Job Limits
Edit workflow file:
```yaml
- name: Scrape New Grad jobs
  run: |
    python -u etl/scrape_jobs.py --level newgrad --max-jobs 50  # Increase to 50
```

### Change Matching Threshold
Edit workflow env vars:
```yaml
env:
  MIN_RELEVANCE_SCORE: 85  # Only notify for scores >= 85
  MAX_DAILY_MATCHES: 30    # Score top 30 jobs
```

## Troubleshooting

### GitHub Actions Fails
1. Check **Actions** tab for error logs
2. Verify all secrets are configured correctly
3. Check Supabase/Groq API quotas

### No Jobs Found
- Google may be rate-limiting
- Try reducing `--max-jobs`
- Check if ATS sites are accessible

### Email Not Sent
- Verify SMTP credentials in secrets
- Check Gmail app password (not regular password)
- Ensure "Less secure app access" is enabled (if using Gmail)

## Local Development

### Test Docker Build
```bash
# Build image
docker build -t jobs-scraper .

# Test scraper
docker run --env-file .env jobs-scraper python etl/scrape_jobs.py --level newgrad --max-jobs 3

# Interactive shell
docker run -it --env-file .env jobs-scraper /bin/bash
```

### Debug Selenium
```bash
# Run with browser visible (requires X11 forwarding)
docker run --env-file .env -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix jobs-scraper python etl/scrape_jobs.py --level newgrad --max-jobs 3 --show-browser
```

## Production Checklist

- [ ] All GitHub secrets configured
- [ ] Workflow schedule set correctly
- [ ] Email notifications tested
- [ ] Supabase tables created (schema.sql)
- [ ] Resume uploaded to database
- [ ] LCA sponsorship data loaded (optional)
- [ ] First workflow run successful
- [ ] Email notification received

## Monitoring

### Check Workflow Status
```bash
# Via GitHub CLI
gh run list --workflow=daily-jobs.yml

# View latest run
gh run view --log
```

### Check Database
```sql
-- Count jobs scraped today
SELECT COUNT(*) FROM jobs 
WHERE scraped_at::date = CURRENT_DATE;

-- View top matches
SELECT * FROM active_matches 
ORDER BY llama_score DESC 
LIMIT 10;
```

## Next Steps

1. **Test locally** with Docker Compose
2. **Configure GitHub secrets**
3. **Enable GitHub Actions**
4. **Monitor first automated run**
5. **Adjust thresholds** based on results
