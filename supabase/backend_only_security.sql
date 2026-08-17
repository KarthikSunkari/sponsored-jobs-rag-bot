-- REVIEW BEFORE APPLYING.
-- This project currently has no public frontend. This policy makes its public
-- schema backend-only: service-role automation keeps working, while anon and
-- ordinary authenticated clients cannot read or modify bot data.

ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_resume ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;

ALTER VIEW public.sponsorship_companies SET (security_invoker = true);
ALTER VIEW public.active_matches SET (security_invoker = true);

REVOKE ALL ON TABLE
    public.companies,
    public.jobs,
    public.job_embeddings,
    public.user_resume,
    public.job_matches,
    public.applications,
    public.sponsorship_companies,
    public.active_matches
FROM anon, authenticated;

ALTER FUNCTION public.update_approval_rate()
SET search_path = public, pg_temp;

ALTER FUNCTION public.match_jobs(vector, double precision, integer)
SET search_path = public, pg_temp;

REVOKE EXECUTE ON FUNCTION public.match_jobs(vector, double precision, integer)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.match_jobs(vector, double precision, integer)
TO service_role;
