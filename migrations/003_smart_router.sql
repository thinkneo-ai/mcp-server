-- ThinkNEO Smart Router — Database migration
-- Run against thinkneo_mcp database

-- 1. Router configurations per organization/API key
CREATE TABLE IF NOT EXISTS router_configs (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL,
    quality_threshold INT DEFAULT 85 CHECK (quality_threshold BETWEEN 0 AND 100),
    max_latency_ms INT,
    preferred_providers TEXT[], -- e.g. {'openai','anthropic'}
    blocked_providers TEXT[],
    budget_limit_daily_usd NUMERIC(10,4),
    budget_limit_monthly_usd NUMERIC(10,4),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (key_hash)
);

-- 2. Individual routed requests
CREATE TABLE IF NOT EXISTS router_requests (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL,
    task_type TEXT NOT NULL,
    model_requested TEXT,
    model_used TEXT NOT NULL,
    provider TEXT NOT NULL,
    cost_original NUMERIC(10,6) NOT NULL DEFAULT 0,
    cost_actual NUMERIC(10,6) NOT NULL DEFAULT 0,
    savings NUMERIC(10,6) GENERATED ALWAYS AS (cost_original - cost_actual) STORED,
    latency_ms INT,
    quality_score INT CHECK (quality_score BETWEEN 0 AND 100),
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    routed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_router_requests_key_date ON router_requests (key_hash, routed_at);
CREATE INDEX IF NOT EXISTS idx_router_requests_task ON router_requests (task_type, routed_at);

-- 3. Daily savings aggregates (materialized by a trigger or cron)
CREATE TABLE IF NOT EXISTS router_savings (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    key_hash TEXT NOT NULL,
    requests_count INT DEFAULT 0,
    total_original_cost NUMERIC(12,6) DEFAULT 0,
    total_actual_cost NUMERIC(12,6) DEFAULT 0,
    total_savings NUMERIC(12,6) GENERATED ALWAYS AS (total_original_cost - total_actual_cost) STORED,
    avg_quality_score NUMERIC(5,2) DEFAULT 0,
    top_model_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, key_hash)
);

CREATE INDEX IF NOT EXISTS idx_router_savings_key_date ON router_savings (key_hash, date);
CREATE INDEX IF NOT EXISTS idx_router_savings_date ON router_savings (date);

-- Grant permissions
GRANT ALL ON router_configs TO mcp_user;
GRANT ALL ON router_requests TO mcp_user;
GRANT ALL ON router_savings TO mcp_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mcp_user;
