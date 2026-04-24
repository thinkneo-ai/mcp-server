-- Plan enforcement — adds a canonical `plan` column to api_keys with
-- values {free, pro, enterprise}. Backward compatible: the existing `tier`
-- column is preserved (used elsewhere for rate limits) and the plan column
-- is populated from tier on migration.

\c thinkneo_mcp

ALTER TABLE api_keys
    ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';

-- Backfill from tier. Existing values seen in prod: 'free', 'enterprise'.
-- We keep 'pro' as a new middle tier.
UPDATE api_keys
    SET plan = 'enterprise'
    WHERE tier = 'enterprise' AND plan = 'free';

-- Enforce allowed values.
ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_plan_check;
ALTER TABLE api_keys
    ADD CONSTRAINT api_keys_plan_check CHECK (plan IN ('free','pro','enterprise'));

CREATE INDEX IF NOT EXISTS idx_api_keys_plan ON api_keys (plan);

GRANT ALL ON api_keys TO mcp_user;
