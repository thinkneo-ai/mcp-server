-- ThinkNEO MCP Server — Database initialization
-- Run as postgres superuser: sudo -u postgres psql -f init_db.sql

-- Create database (idempotent-ish via check)
SELECT 'CREATE DATABASE thinkneo_mcp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'thinkneo_mcp')\gexec

-- Create user (idempotent)
-- IMPORTANT: Set the password via environment variable or replace the placeholder below.
-- Run: sudo -u postgres psql -c "CREATE USER mcp_user WITH PASSWORD '$(cat /opt/thinkneo-mcp-server/.env | grep MCP_DB_PASSWORD | cut -d= -f2)';"
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mcp_user') THEN
        RAISE NOTICE 'User mcp_user does not exist — create it manually with a secure password:';
        RAISE NOTICE 'CREATE USER mcp_user WITH PASSWORD ''your_secure_password'';';
    END IF;
END $$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE thinkneo_mcp TO mcp_user;

-- Connect to the database and create tables
\c thinkneo_mcp

-- Grant schema usage
GRANT ALL ON SCHEMA public TO mcp_user;

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash TEXT PRIMARY KEY,
    key_prefix TEXT NOT NULL,
    email TEXT,
    tier TEXT DEFAULT 'free',
    monthly_limit INT DEFAULT 500,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_log (
    id BIGSERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    ip TEXT,
    region TEXT,
    called_at TIMESTAMPTZ DEFAULT NOW(),
    cost_estimate_usd NUMERIC(10,6) DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_usage_key_month ON usage_log (key_hash, called_at);
CREATE INDEX IF NOT EXISTS idx_usage_tool ON usage_log (tool_name, called_at);

-- Grant table permissions to mcp_user
GRANT ALL ON ALL TABLES IN SCHEMA public TO mcp_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO mcp_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO mcp_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO mcp_user;
