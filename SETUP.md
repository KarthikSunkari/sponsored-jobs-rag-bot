# Quick Setup Guide

## Prerequisites Checklist

Before running the system, make sure you have:

- [x] **Supabase Account** - Database tables created
- [x] **Groq API Key** - Added to `.env` file
- [ ] **Supabase Credentials** - Need to add to `.env` file
- [ ] **Gmail App Password** - For email notifications (optional for now)

## Required: Update .env File

You need to add your Supabase credentials to the `.env` file:

1. Go to your Supabase project dashboard
2. Click on **Settings** → **API**
3. Copy the following values:
   - **Project URL** → `SUPABASE_URL`
   - **anon/public key** → `SUPABASE_KEY`
   - **service_role key** → `SUPABASE_SERVICE_KEY`

4. Update `.env` file:
   ```bash
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_KEY=your-anon-key-here
   SUPABASE_SERVICE_KEY=your-service-role-key-here
   ```

## Optional: Gmail App Password (for email notifications)

To enable email notifications:

1. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
2. Create a new app password for "Mail"
3. Copy the 16-character password
4. Update `.env`:
   ```bash
   SMTP_PASSWORD=your-16-char-app-password
   ```

## Quick Test Commands

Once `.env` is configured:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Test Supabase connection
python -c "from utils.supabase_client import get_supabase_client; get_supabase_client(); print('✅ Connected')"

# 3. Test Groq API
python agents/groq_client.py

# 4. Upload resume
python utils/resume_extractor.py

# 5. Scrape 5 jobs (quick test)
python etl/scrape_jobs.py --level newgrad --max-jobs 5

# 6. Match jobs
python rag/match_jobs.py
```

## Full End-to-End Test

```bash
./test_pipeline.sh
```

This will:
- ✅ Check prerequisites
- ✅ Install dependencies
- ✅ Test Supabase connection
- ✅ Test Groq API
- ✅ Upload resume
- ✅ Scrape 20 jobs (10 new grad + 10 mid-level)
- ✅ Run job matching pipeline
- ✅ Display top matches

## What to Expect

After running the pipeline, you should see:
- Jobs stored in Supabase `jobs` table
- Job embeddings in `job_embeddings` table
- Resume in `user_resume` table
- Matched jobs in `job_matches` table with Llama-3 scores
- Top 10 matches displayed in terminal

## Next Steps

1. **Update `.env`** with your Supabase credentials
2. **Run** `pip install -r requirements.txt`
3. **Test** individual components or run full pipeline
4. **Review** matches in Supabase dashboard or terminal output
