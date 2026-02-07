# GitHub Actions Deployment Guide

## 🚀 Quick Deploy (3 Steps)

Your code is already on GitHub! Now just add secrets and enable Actions.

---

## Step 1: Add GitHub Secrets

Go to your repository: https://github.com/KarthikSunkari/sponsored-jobs-rag-bot

Navigate to: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these **11 secrets**:

| Secret Name | Where to Find Value |
|-------------|---------------------|
| `SUPABASE_URL` | From your `.env` file |
| `SUPABASE_KEY` | From your `.env` file (anon key) |
| `SUPABASE_SERVICE_KEY` | From your `.env` file (service_role key) |
| `GROQ_API_KEY` | From your `.env` file |
| `GROQ_MODEL` | `llama-3.1-8b-instant` |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your Gmail address |
| `SMTP_PASSWORD` | Gmail app password from `.env` |
| `NOTIFICATION_EMAIL` | Your email address |
| `SERPAPI_KEY` | From your `.env` file |

**Pro tip:** Just copy values from your local `.env` file!

---

## Step 2: Enable GitHub Actions

1. Go to **Actions** tab: https://github.com/KarthikSunkari/sponsored-jobs-rag-bot/actions
2. Click **"I understand my workflows, go ahead and enable them"**
3. You should see: **"Daily Job Scraper"** workflow

---

## Step 3: Test Run

### Manual Trigger (Recommended for First Test)
1. Click **"Daily Job Scraper"** workflow
2. Click **"Run workflow"** dropdown (top right)
3. Click green **"Run workflow"** button
4. Wait 2-3 minutes
5. **Check your email!** 📧

### Scheduled Run
- Runs automatically at **9 AM EST (2 PM UTC)** daily
- First scheduled run will be tomorrow morning

---

## 📊 Monitor the Run

1. Go to **Actions** tab
2. Click on the running workflow
3. View logs for each job:
   - `scrape-newgrad-jobs` - Scraping new grad positions
   - `scrape-midlevel-jobs` - Scraping mid-level positions
   - `match-jobs` - Matching jobs to resume
   - `send-notifications` - Sending email

### Expected Output:
```
✅ SerpAPI Success: X jobs found
✅ Groq scoring complete: 5 matches (82-92/100)
✅ Email sent to your-email@gmail.com
```

---

## 🎉 You're Live!

Your automated job bot is now running on GitHub Actions!

**What happens daily:**
- ✅ Scrapes 50 jobs using SerpAPI (100% reliable)
- ✅ Matches against your resume using vector search
- ✅ Scores relevance with Llama-3 (Groq)
- ✅ Emails top matches (score ≥ 80) with sponsorship data

**Cost:** $0/month (all free tiers)

---

## 🔧 Troubleshooting

### No jobs found?
- Check SerpAPI quota (100 searches/month)
- Verify all 11 secrets are added correctly
- Check Actions logs for errors

### No email received?
- Check spam folder
- Verify Gmail app password is correct
- Ensure at least one match has score ≥ 80

### Workflow failed?
- Verify all 11 secrets are added
- Check Docker build logs
- Review error messages in Actions

---

## ✅ Deployment Checklist

- [ ] All 11 secrets added to GitHub
- [ ] GitHub Actions enabled
- [ ] Manual test run successful
- [ ] Email received with job matches
- [ ] Logs reviewed (no errors)

**Once all checked, you're done!** 🚀

---

## 📈 Next Steps

### Monitor Daily Runs
- Check email at 9 AM EST for job matches
- Review GitHub Actions for any failures
- Adjust match threshold if needed

### Improve Extraction (Optional)
- Add HTML parsers for more ATS platforms
- Extract full job descriptions
- Better matching with complete data

### Customize
- Adjust search queries in `etl/search_queries.yaml`
- Change schedule in `.github/workflows/daily-jobs.yml`
- Modify match threshold (default: 80)

---

## 🆘 Need Help?

**Common Issues:**
- Secrets not working → Double-check spelling and values
- No jobs extracted → Expected, will improve iteratively
- Rate limits → SerpAPI has 100/month, Groq has 30 req/min

**System is working if:**
- ✅ SerpAPI finds job URLs
- ✅ Email is sent (even with 0 matches initially)
- ✅ No errors in Actions logs
