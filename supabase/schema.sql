-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Companies table: stores sponsorship history
CREATE TABLE IF NOT EXISTS companies (
    id BIGSERIAL PRIMARY KEY,
    employer_name TEXT NOT NULL UNIQUE,
    naics_code TEXT,
    total_approvals INTEGER DEFAULT 0,
    total_denials INTEGER DEFAULT 0,
    approval_rate DECIMAL(5,2),
    h1b_approvals INTEGER DEFAULT 0,
    h1b_denials INTEGER DEFAULT 0,
    perm_approvals INTEGER DEFAULT 0,
    perm_denials INTEGER DEFAULT 0,
    lca_approvals INTEGER DEFAULT 0,
    lca_denials INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast company lookups
CREATE INDEX idx_companies_employer_name ON companies(employer_name);
CREATE INDEX idx_companies_approval_rate ON companies(approval_rate DESC);

-- Jobs table: stores scraped job listings
CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT REFERENCES companies(id),
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    job_url TEXT UNIQUE NOT NULL,
    url_hash TEXT UNIQUE NOT NULL,
    source TEXT, -- 'linkedin', 'indeed', 'github', 'remoteok'
    posted_date TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for job queries
CREATE INDEX idx_jobs_company_id ON jobs(company_id);
CREATE INDEX idx_jobs_url_hash ON jobs(url_hash);
CREATE INDEX idx_jobs_is_active ON jobs(is_active);
CREATE INDEX idx_jobs_scraped_at ON jobs(scraped_at DESC);

-- Job embeddings table: stores vector embeddings for semantic search
CREATE TABLE IF NOT EXISTS job_embeddings (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT REFERENCES jobs(id) ON DELETE CASCADE,
    embedding vector(384), -- all-MiniLM-L6-v2 dimension
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX idx_job_embeddings_vector ON job_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- User resume table: stores user resume and embeddings
CREATE TABLE IF NOT EXISTS user_resume (
    id BIGSERIAL PRIMARY KEY,
    resume_text TEXT NOT NULL,
    embedding vector(384),
    skills TEXT[], -- extracted skills
    experience_years INTEGER,
    updated_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Job matches table: stores scored matches between resume and jobs
CREATE TABLE IF NOT EXISTS job_matches (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id BIGINT REFERENCES user_resume(id),
    cosine_similarity DECIMAL(5,4), -- from pgvector
    llama_score INTEGER, -- 0-100 from Llama-3
    llama_reasoning TEXT,
    is_notified BOOLEAN DEFAULT FALSE,
    matched_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for match queries
CREATE INDEX idx_job_matches_job_id ON job_matches(job_id);
CREATE INDEX idx_job_matches_llama_score ON job_matches(llama_score DESC);
CREATE INDEX idx_job_matches_is_notified ON job_matches(is_notified);

-- Application tracking table: tracks job applications
CREATE TABLE IF NOT EXISTS applications (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT REFERENCES jobs(id),
    status TEXT DEFAULT 'not_applied', -- 'not_applied', 'applied', 'interviewing', 'rejected', 'accepted'
    applied_at TIMESTAMP,
    last_updated TIMESTAMP DEFAULT NOW(),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for application tracking
CREATE INDEX idx_applications_job_id ON applications(job_id);
CREATE INDEX idx_applications_status ON applications(status);

-- Function to calculate approval rate
CREATE OR REPLACE FUNCTION update_approval_rate()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.total_approvals + NEW.total_denials) > 0 THEN
        NEW.approval_rate := (NEW.total_approvals::DECIMAL / (NEW.total_approvals + NEW.total_denials)) * 100;
    ELSE
        NEW.approval_rate := 0;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-calculate approval rate
CREATE TRIGGER trigger_update_approval_rate
BEFORE INSERT OR UPDATE ON companies
FOR EACH ROW
EXECUTE FUNCTION update_approval_rate();

-- View for high-quality sponsorship companies (>70% approval, >3 approvals)
CREATE OR REPLACE VIEW sponsorship_companies AS
SELECT 
    id,
    employer_name,
    naics_code,
    total_approvals,
    total_denials,
    approval_rate,
    h1b_approvals,
    perm_approvals,
    lca_approvals
FROM companies
WHERE approval_rate >= 70 
  AND total_approvals >= 3
ORDER BY approval_rate DESC, total_approvals DESC;

-- View for active job matches with company info
CREATE OR REPLACE VIEW active_matches AS
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
    jm.matched_at
FROM job_matches jm
JOIN jobs j ON jm.job_id = j.id
JOIN companies c ON j.company_id = c.id
WHERE j.is_active = TRUE
  AND jm.llama_score >= 80
ORDER BY jm.llama_score DESC, jm.matched_at DESC;

