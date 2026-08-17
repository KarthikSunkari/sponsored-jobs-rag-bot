-- Run once on databases created before job_matches enforced one row per
-- resume/job pair. Keeps the newest score, then adds the upsert target used by
-- the application.
DELETE FROM job_matches older
USING job_matches newer
WHERE older.job_id = newer.job_id
  AND older.resume_id = newer.resume_id
  AND (older.matched_at, older.id) < (newer.matched_at, newer.id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_matches_job_resume
ON job_matches(job_id, resume_id);
