-- Trust Score system — AI governance scoring for organizations
-- Migration 004: Creates the trust_scores table

\c thinkneo_mcp

CREATE TABLE IF NOT EXISTS trust_scores (
    id              SERIAL PRIMARY KEY,
    api_key_hash    TEXT NOT NULL,
    org_name        TEXT,
    score           INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    breakdown       JSONB NOT NULL DEFAULT '{}',
    badge_level     TEXT NOT NULL CHECK (badge_level IN ('platinum','gold','silver','bronze','unrated')),
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until     TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
    report_token    TEXT UNIQUE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trust_scores_key_hash ON trust_scores (api_key_hash);
CREATE INDEX IF NOT EXISTS idx_trust_scores_report_token ON trust_scores (report_token);
CREATE INDEX IF NOT EXISTS idx_trust_scores_valid_until ON trust_scores (valid_until);

GRANT ALL ON trust_scores TO mcp_user;
GRANT USAGE, SELECT ON SEQUENCE trust_scores_id_seq TO mcp_user;
