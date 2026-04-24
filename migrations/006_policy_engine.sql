-- Migration 006: Policy Engine — Governance-as-Code
-- Date: 2026-04-24

CREATE TABLE IF NOT EXISTS policies (
    id BIGSERIAL PRIMARY KEY,
    policy_id UUID NOT NULL DEFAULT gen_random_uuid(),
    api_key_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    version INTEGER DEFAULT 1,
    enabled BOOLEAN DEFAULT TRUE,
    scope JSONB DEFAULT '{}',           -- {agents: ["*"], actions: ["*"]}
    conditions JSONB NOT NULL,          -- [{field, operator, value}]
    effect TEXT NOT NULL DEFAULT 'block', -- 'block', 'warn', 'require_approval', 'log'
    notification JSONB DEFAULT '{}',    -- {channel, target}
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(api_key_hash, name, version)
);

CREATE TABLE IF NOT EXISTS policy_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id UUID NOT NULL DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL,
    api_key_hash TEXT NOT NULL,
    agent_name TEXT,
    action TEXT,
    context JSONB DEFAULT '{}',
    effect TEXT NOT NULL,               -- what the policy decided
    rule_matched TEXT,                  -- which condition triggered
    evaluated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS policy_violations (
    id BIGSERIAL PRIMARY KEY,
    violation_id UUID NOT NULL DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL,
    policy_name TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    agent_name TEXT,
    action TEXT,
    context JSONB DEFAULT '{}',
    effect TEXT NOT NULL,
    message TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    violated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policies_key ON policies (api_key_hash);
CREATE INDEX IF NOT EXISTS idx_policies_enabled ON policies (api_key_hash, enabled) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_policy_evals_key ON policy_evaluations (api_key_hash, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_policy_violations_key ON policy_violations (api_key_hash, violated_at DESC);
CREATE INDEX IF NOT EXISTS idx_policy_violations_unresolved ON policy_violations (api_key_hash) WHERE resolved = FALSE;
