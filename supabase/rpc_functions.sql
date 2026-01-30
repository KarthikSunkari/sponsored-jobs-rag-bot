-- RPC function for vector similarity search
-- This should be run in Supabase SQL Editor after schema.sql

CREATE OR REPLACE FUNCTION match_jobs(
  query_embedding vector(384),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  job_id bigint,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    job_embeddings.job_id,
    1 - (job_embeddings.embedding <=> query_embedding) as similarity
  FROM job_embeddings
  WHERE 1 - (job_embeddings.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
$$;
