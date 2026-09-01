-- Adds independently matchable resume profiles without deleting the existing
-- resume. This migration intentionally does not alter RLS policy.
ALTER TABLE public.user_resume
ADD COLUMN IF NOT EXISTS profile_name TEXT,
ADD COLUMN IF NOT EXISTS target_roles TEXT[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE public.user_resume
SET profile_name = 'SDE'
WHERE profile_name IS NULL OR btrim(profile_name) = '';

ALTER TABLE public.user_resume
ALTER COLUMN profile_name SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_resume_profile_name_lower
ON public.user_resume (lower(profile_name));

CREATE OR REPLACE VIEW public.active_matches
WITH (security_invoker = true) AS
SELECT
    jm.id,
    jm.job_id,
    j.title,
    j.location,
    j.salary_min,
    j.salary_max,
    j.job_url,
    c.employer_name,
    c.approval_rate,
    jm.cosine_similarity,
    jm.llama_score,
    jm.llama_reasoning,
    jm.is_notified,
    jm.matched_at,
    ur.profile_name AS resume_profile,
    c.total_approvals,
    c.h1b_approvals,
    c.perm_approvals,
    c.lca_approvals
FROM public.job_matches jm
JOIN public.jobs j ON jm.job_id = j.id
LEFT JOIN public.companies c ON j.company_id = c.id
JOIN public.user_resume ur ON jm.resume_id = ur.id
WHERE j.is_active = TRUE
ORDER BY jm.llama_score DESC, jm.matched_at DESC;
