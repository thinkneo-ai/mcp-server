-- Migration 007: Outcome Benchmarking — Quality-Based Routing
-- Date: 2026-04-24

CREATE TABLE IF NOT EXISTS outcome_benchmarks (
    id BIGSERIAL PRIMARY KEY,
    api_key_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL,
    quality_score NUMERIC(5,2) DEFAULT 0,       -- rolling average 0-100
    sample_count INTEGER DEFAULT 0,
    verified_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    avg_latency_ms INTEGER DEFAULT 0,
    avg_cost_usd NUMERIC(10,6) DEFAULT 0,
    cost_per_quality_point NUMERIC(10,6) DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(api_key_hash, provider, model, task_type)
);

CREATE TABLE IF NOT EXISTS outcome_feedback (
    id BIGSERIAL PRIMARY KEY,
    api_key_hash TEXT NOT NULL,
    claim_id UUID,
    session_id UUID,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL,
    quality_signal TEXT NOT NULL,        -- 'verified', 'failed', 'thumbs_up', 'thumbs_down'
    quality_score NUMERIC(5,2),
    feedback_source TEXT,               -- 'outcome_validation', 'user_feedback', 'auto_eval'
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_benchmarks_key ON outcome_benchmarks (api_key_hash);
CREATE INDEX IF NOT EXISTS idx_benchmarks_lookup ON outcome_benchmarks (api_key_hash, task_type);
CREATE INDEX IF NOT EXISTS idx_feedback_key ON outcome_feedback (api_key_hash, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_provider ON outcome_feedback (provider, model, task_type);
