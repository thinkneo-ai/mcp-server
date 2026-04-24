-- Migration 005: Outcome Validation Loop
-- "The agent said it did it. Did it actually happen?"
-- Date: 2026-04-24

-- Claims: agent-registered action claims awaiting verification
CREATE TABLE IF NOT EXISTS outcome_claims (
    id BIGSERIAL PRIMARY KEY,
    claim_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID,                            -- optional link to observability session
    api_key_hash TEXT NOT NULL,
    agent_name TEXT,
    action TEXT NOT NULL,                        -- 'email_sent', 'pr_created', 'file_written', 'http_request', 'db_insert', 'payment_processed'
    target TEXT NOT NULL,                        -- 'user@example.com', 'repo/pr/123', '/path/to/file'
    evidence_type TEXT NOT NULL,                 -- 'http_status', 'smtp_delivery', 'db_row_exists', 'file_exists', 'manual', 'webhook'
    claim_metadata JSONB DEFAULT '{}',          -- extra context from the agent
    status TEXT NOT NULL DEFAULT 'pending',      -- 'pending', 'verifying', 'verified', 'failed', 'expired', 'skipped'
    verified_at TIMESTAMPTZ,
    evidence JSONB,                             -- raw verification data from the adapter
    verifier TEXT,                               -- which adapter verified: 'http_adapter', 'smtp_adapter', etc.
    failure_reason TEXT,                         -- why verification failed
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
    CONSTRAINT chk_claim_status CHECK (status IN ('pending', 'verifying', 'verified', 'failed', 'expired', 'skipped'))
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_claims_key_hash ON outcome_claims (api_key_hash);
CREATE INDEX IF NOT EXISTS idx_claims_status ON outcome_claims (status) WHERE status IN ('pending', 'verifying');
CREATE INDEX IF NOT EXISTS idx_claims_claim_id ON outcome_claims (claim_id);
CREATE INDEX IF NOT EXISTS idx_claims_session ON outcome_claims (session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_claims_expires ON outcome_claims (expires_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_claims_action ON outcome_claims (action, api_key_hash);

-- Verification stats: pre-aggregated daily metrics
CREATE TABLE IF NOT EXISTS verification_stats_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    api_key_hash TEXT NOT NULL,
    total_claims INTEGER DEFAULT 0,
    verified_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    expired_count INTEGER DEFAULT 0,
    pending_count INTEGER DEFAULT 0,
    verification_rate NUMERIC(5,2) DEFAULT 0,   -- verified / (verified + failed) * 100
    avg_verification_time_ms INTEGER DEFAULT 0,
    top_action TEXT,
    top_failure_reason TEXT,
    UNIQUE(date, api_key_hash)
);

CREATE INDEX IF NOT EXISTS idx_vstats_key ON verification_stats_daily (api_key_hash, date DESC);
