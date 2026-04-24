-- Migration 008: Compliance Export
-- Date: 2026-04-24

CREATE TABLE IF NOT EXISTS compliance_reports (
    id BIGSERIAL PRIMARY KEY,
    report_id UUID NOT NULL DEFAULT gen_random_uuid(),
    api_key_hash TEXT NOT NULL,
    framework TEXT NOT NULL,         -- 'lgpd', 'iso_42001', 'eu_ai_act'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    report_data JSONB NOT NULL,
    compliance_score NUMERIC(5,2),
    report_hash TEXT NOT NULL,       -- SHA-256 of report_data
    download_token TEXT UNIQUE NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_compliance_key ON compliance_reports (api_key_hash, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_compliance_token ON compliance_reports (download_token);
