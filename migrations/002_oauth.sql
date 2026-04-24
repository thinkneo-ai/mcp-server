-- OAuth 2.0 tables for ThinkNEO MCP Server
-- Enables Claude Desktop, Cursor, and other MCP clients that require OAuth discovery.
-- Backward-compatible: OAuth access tokens resolve to existing api_keys rows.

\c thinkneo_mcp

-- Dynamically registered clients (RFC 7591) or pre-provisioned public clients.
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id                   TEXT PRIMARY KEY,
    client_secret_hash          TEXT,                 -- NULL for public clients (PKCE-only)
    client_name                 TEXT,
    redirect_uris               TEXT[] NOT NULL,
    grant_types                 TEXT[] NOT NULL DEFAULT ARRAY['authorization_code','refresh_token'],
    response_types              TEXT[] NOT NULL DEFAULT ARRAY['code'],
    token_endpoint_auth_method  TEXT   NOT NULL DEFAULT 'none',
    scope                       TEXT   DEFAULT 'mcp',
    software_id                 TEXT,
    software_version            TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- Short-lived authorization codes (max 10 min TTL). PKCE required.
CREATE TABLE IF NOT EXISTS oauth_auth_codes (
    code                   TEXT PRIMARY KEY,           -- random, single-use
    client_id              TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    redirect_uri           TEXT NOT NULL,
    code_challenge         TEXT NOT NULL,
    code_challenge_method  TEXT NOT NULL,              -- 'S256' required by MCP spec
    scope                  TEXT,
    api_key_hash           TEXT NOT NULL,              -- resolved ThinkNEO api_keys.key_hash
    api_key                TEXT NOT NULL,              -- raw api key (short TTL + single-use → safe)
    resource               TEXT,                       -- RFC 8707 resource indicator
    expires_at             TIMESTAMPTZ NOT NULL,
    used                   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oauth_codes_expires ON oauth_auth_codes (expires_at);

-- Access tokens issued by /oauth/token. SHA-256 hashed before storage.
CREATE TABLE IF NOT EXISTS oauth_access_tokens (
    token_hash     TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    api_key        TEXT NOT NULL,                      -- underlying ThinkNEO api key (used for DB lookups downstream)
    api_key_hash   TEXT NOT NULL,
    scope          TEXT,
    resource       TEXT,
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_expires ON oauth_access_tokens (expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_apikey  ON oauth_access_tokens (api_key_hash);

-- Refresh tokens.
CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
    token_hash     TEXT PRIMARY KEY,
    client_id      TEXT NOT NULL REFERENCES oauth_clients(client_id) ON DELETE CASCADE,
    api_key        TEXT NOT NULL,
    api_key_hash   TEXT NOT NULL,
    scope          TEXT,
    resource       TEXT,
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oauth_refresh_expires ON oauth_refresh_tokens (expires_at);

GRANT ALL ON oauth_clients, oauth_auth_codes, oauth_access_tokens, oauth_refresh_tokens TO mcp_user;
