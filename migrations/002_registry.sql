-- ThinkNEO MCP Marketplace Registry — Database migration
-- Run: ssh root@100.75.242.28 then: sudo -u postgres psql -d thinkneo_mcp -f /tmp/002_registry.sql

-- ============================================================
-- 1. Main registry table
-- ============================================================
CREATE TABLE IF NOT EXISTS mcp_registry (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    author          TEXT NOT NULL DEFAULT '',
    author_email    TEXT DEFAULT '',
    version         TEXT NOT NULL DEFAULT '1.0.0',
    endpoint_url    TEXT NOT NULL,
    transport       TEXT NOT NULL DEFAULT 'streamable-http'
                        CHECK (transport IN ('streamable-http', 'sse', 'stdio')),
    tools_count     INTEGER NOT NULL DEFAULT 0,
    tools_list      JSONB DEFAULT '[]'::jsonb,
    categories      TEXT[] DEFAULT '{}',
    tags            TEXT[] DEFAULT '{}',
    readme          TEXT DEFAULT '',
    icon_url        TEXT DEFAULT '',
    repo_url        TEXT DEFAULT '',
    license         TEXT DEFAULT 'MIT',
    downloads       INTEGER NOT NULL DEFAULT 0,
    stars           INTEGER NOT NULL DEFAULT 0,
    verified        BOOLEAN NOT NULL DEFAULT FALSE,
    security_score  INTEGER DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_registry_name ON mcp_registry (name);
CREATE INDEX IF NOT EXISTS idx_registry_categories ON mcp_registry USING GIN (categories);
CREATE INDEX IF NOT EXISTS idx_registry_tags ON mcp_registry USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_registry_verified ON mcp_registry (verified);
CREATE INDEX IF NOT EXISTS idx_registry_downloads ON mcp_registry (downloads DESC);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_registry_fts ON mcp_registry USING GIN (
    to_tsvector('english', coalesce(name, '') || ' ' || coalesce(display_name, '') || ' ' || coalesce(description, ''))
);

-- ============================================================
-- 2. Version history
-- ============================================================
CREATE TABLE IF NOT EXISTS mcp_registry_versions (
    id          BIGSERIAL PRIMARY KEY,
    registry_id BIGINT NOT NULL REFERENCES mcp_registry(id) ON DELETE CASCADE,
    version     TEXT NOT NULL,
    changelog   TEXT DEFAULT '',
    tools_list  JSONB DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_registry_versions_rid ON mcp_registry_versions (registry_id);

-- ============================================================
-- 3. Reviews
-- ============================================================
CREATE TABLE IF NOT EXISTS mcp_registry_reviews (
    id          BIGSERIAL PRIMARY KEY,
    registry_id BIGINT NOT NULL REFERENCES mcp_registry(id) ON DELETE CASCADE,
    api_key_hash TEXT NOT NULL,
    rating      INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment     TEXT DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (registry_id, api_key_hash)          -- one review per user per package
);

CREATE INDEX IF NOT EXISTS idx_registry_reviews_rid ON mcp_registry_reviews (registry_id);

-- ============================================================
-- 4. Install tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS mcp_registry_installs (
    id          BIGSERIAL PRIMARY KEY,
    registry_id BIGINT NOT NULL REFERENCES mcp_registry(id) ON DELETE CASCADE,
    api_key_hash TEXT DEFAULT 'anonymous',
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_type TEXT NOT NULL DEFAULT 'custom'
                    CHECK (client_type IN ('claude-desktop', 'cursor', 'windsurf', 'custom'))
);

CREATE INDEX IF NOT EXISTS idx_registry_installs_rid ON mcp_registry_installs (registry_id);
CREATE INDEX IF NOT EXISTS idx_registry_installs_client ON mcp_registry_installs (client_type);

-- ============================================================
-- Permissions
-- ============================================================
GRANT ALL ON ALL TABLES IN SCHEMA public TO mcp_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO mcp_user;
