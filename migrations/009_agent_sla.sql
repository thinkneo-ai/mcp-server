-- Migration 009: Agent SLA / Outcome SLA
-- Date: 2026-04-24

CREATE TABLE IF NOT EXISTS agent_slas (
    id BIGSERIAL PRIMARY KEY,
    sla_id UUID NOT NULL DEFAULT gen_random_uuid(),
    api_key_hash TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    metric TEXT NOT NULL,            -- 'accuracy', 'response_quality', 'cost_efficiency', 'safety', 'latency'
    threshold NUMERIC(10,4) NOT NULL, -- target value
    threshold_direction TEXT NOT NULL DEFAULT 'min', -- 'min' (must be >= threshold) or 'max' (must be <= threshold)
    sla_window TEXT NOT NULL DEFAULT '7d', -- '1h', '24h', '7d', '30d'
    breach_action TEXT NOT NULL DEFAULT 'alert', -- 'alert', 'escalate', 'disable', 'switch_model'
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(api_key_hash, agent_name, metric)
);

CREATE TABLE IF NOT EXISTS sla_breaches (
    id BIGSERIAL PRIMARY KEY,
    breach_id UUID NOT NULL DEFAULT gen_random_uuid(),
    sla_id UUID NOT NULL,
    api_key_hash TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    metric TEXT NOT NULL,
    threshold NUMERIC(10,4),
    actual_value NUMERIC(10,4),
    breach_action TEXT NOT NULL,
    action_taken BOOLEAN DEFAULT FALSE,
    action_result TEXT,
    breached_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_slas_key ON agent_slas (api_key_hash);
CREATE INDEX IF NOT EXISTS idx_slas_agent ON agent_slas (api_key_hash, agent_name);
CREATE INDEX IF NOT EXISTS idx_breaches_key ON sla_breaches (api_key_hash, breached_at DESC);
CREATE INDEX IF NOT EXISTS idx_breaches_unresolved ON sla_breaches (api_key_hash) WHERE resolved_at IS NULL;
