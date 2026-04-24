-- ThinkNEO MCP Marketplace — Seed data
-- Run after 002_registry.sql

-- ============================================================
-- 1. ThinkNEO Control Plane (verified, self-hosted)
-- ============================================================
INSERT INTO mcp_registry (
    name, display_name, description, author, author_email,
    version, endpoint_url, transport, tools_count, tools_list,
    categories, tags, readme, repo_url, license,
    downloads, stars, verified, security_score, published_at
) VALUES (
    'thinkneo-control-plane',
    'ThinkNEO Control Plane',
    'Enterprise AI governance MCP server. 22+ tools for prompt safety checks, spend tracking, policy enforcement, compliance monitoring, provider health, budget management, and MCP marketplace registry. The governance layer between your AI applications and providers.',
    'ThinkNEO',
    'hello@thinkneo.ai',
    '1.1.0',
    'https://mcp.thinkneo.ai/mcp',
    'streamable-http',
    17,
    '[
        {"name": "thinkneo_check", "description": "Free prompt safety check — detects injection & PII"},
        {"name": "thinkneo_usage", "description": "Usage stats — calls, limits, cost"},
        {"name": "thinkneo_read_memory", "description": "Read project memory files"},
        {"name": "thinkneo_write_memory", "description": "Write/update project memory files"},
        {"name": "thinkneo_provider_status", "description": "Real-time provider health for 7 AI providers"},
        {"name": "thinkneo_schedule_demo", "description": "Book a demo with ThinkNEO team"},
        {"name": "thinkneo_check_spend", "description": "AI cost breakdown by provider/model/team"},
        {"name": "thinkneo_evaluate_guardrail", "description": "Pre-flight prompt safety evaluation"},
        {"name": "thinkneo_check_policy", "description": "Verify model/provider/action is allowed"},
        {"name": "thinkneo_get_budget_status", "description": "Budget utilization and enforcement"},
        {"name": "thinkneo_list_alerts", "description": "Active alerts and incidents"},
        {"name": "thinkneo_get_compliance_status", "description": "SOC2/GDPR/HIPAA readiness"},
        {"name": "thinkneo_registry_search", "description": "Search the MCP Marketplace"},
        {"name": "thinkneo_registry_get", "description": "Get full details for an MCP package"},
        {"name": "thinkneo_registry_publish", "description": "Publish an MCP server to the marketplace"},
        {"name": "thinkneo_registry_review", "description": "Rate and review an MCP server"},
        {"name": "thinkneo_registry_install", "description": "Get installation config for an MCP server"}
    ]'::jsonb,
    ARRAY['governance', 'security', 'analytics'],
    ARRAY['ai', 'governance', 'security', 'mcp', 'enterprise', 'compliance', 'prompt-safety', 'budget', 'marketplace'],
    '# ThinkNEO Control Plane

The enterprise AI governance layer — exposed as a remote MCP server.

## Features
- **Prompt Safety**: Free-tier injection detection and PII scanning
- **Spend Tracking**: Cost breakdown by provider, model, team
- **Policy Enforcement**: Verify actions against governance policies
- **Compliance**: SOC2, GDPR, HIPAA readiness monitoring
- **Provider Health**: Real-time status of 7+ AI providers
- **Budget Management**: Utilization tracking and enforcement
- **MCP Marketplace**: Discover, publish, and install MCP servers

## Quick Start
```json
{
  "mcpServers": {
    "thinkneo": {
      "url": "https://mcp.thinkneo.ai/mcp"
    }
  }
}
```

500 free calls/month. No credit card required.

## Links
- Website: https://thinkneo.ai
- Docs: https://mcp.thinkneo.ai/mcp/docs
- GitHub: https://github.com/thinkneo-ai/mcp-server',
    'https://github.com/thinkneo-ai/mcp-server',
    'MIT',
    0, 0, TRUE, 100, NOW()
) ON CONFLICT (name) DO UPDATE SET
    tools_count = EXCLUDED.tools_count,
    tools_list = EXCLUDED.tools_list,
    description = EXCLUDED.description,
    version = EXCLUDED.version,
    security_score = EXCLUDED.security_score,
    updated_at = NOW();

-- Version entry for thinkneo-control-plane
INSERT INTO mcp_registry_versions (registry_id, version, changelog, tools_list)
SELECT id, '1.1.0', 'Added MCP Marketplace Registry (5 new tools)', tools_list
FROM mcp_registry WHERE name = 'thinkneo-control-plane'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 2. Filesystem (Anthropic reference server)
-- ============================================================
INSERT INTO mcp_registry (
    name, display_name, description, author,
    version, endpoint_url, transport, tools_count, tools_list,
    categories, tags, repo_url, license,
    verified, security_score
) VALUES (
    'filesystem',
    'Filesystem',
    'Anthropic reference MCP server for local file system access. Read, write, search, and manage files and directories. Provides tools for file operations with configurable access controls.',
    'Anthropic',
    '0.6.2',
    'npx:@modelcontextprotocol/server-filesystem',
    'stdio',
    11,
    '[
        {"name": "read_file", "description": "Read complete contents of a file"},
        {"name": "read_multiple_files", "description": "Read multiple files simultaneously"},
        {"name": "write_file", "description": "Create or overwrite a file"},
        {"name": "edit_file", "description": "Make selective edits using advanced pattern matching"},
        {"name": "create_directory", "description": "Create a new directory or ensure it exists"},
        {"name": "list_directory", "description": "List directory contents with [FILE] or [DIR] prefixes"},
        {"name": "directory_tree", "description": "Recursive directory listing as JSON"},
        {"name": "move_file", "description": "Move or rename files and directories"},
        {"name": "search_files", "description": "Recursively search for files matching a pattern"},
        {"name": "get_file_info", "description": "Get detailed metadata about a file or directory"},
        {"name": "list_allowed_directories", "description": "Returns the list of directories the server can access"}
    ]'::jsonb,
    ARRAY['development', 'productivity'],
    ARRAY['filesystem', 'files', 'local', 'reference', 'anthropic'],
    'https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem',
    'MIT',
    FALSE, NULL
) ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 3. GitHub (official)
-- ============================================================
INSERT INTO mcp_registry (
    name, display_name, description, author,
    version, endpoint_url, transport, tools_count, tools_list,
    categories, tags, repo_url, license,
    verified, security_score
) VALUES (
    'github',
    'GitHub',
    'Official GitHub MCP server. Manage repositories, issues, pull requests, branches, files, and more through the GitHub API. Requires a GitHub Personal Access Token.',
    'GitHub',
    '0.1.0',
    'npx:@modelcontextprotocol/server-github',
    'stdio',
    19,
    '[
        {"name": "create_or_update_file", "description": "Create or update a single file in a repository"},
        {"name": "search_repositories", "description": "Search for GitHub repositories"},
        {"name": "create_repository", "description": "Create a new GitHub repository"},
        {"name": "get_file_contents", "description": "Get the contents of a file or directory"},
        {"name": "push_files", "description": "Push multiple files to a repository"},
        {"name": "create_issue", "description": "Create a new issue in a repository"},
        {"name": "create_pull_request", "description": "Create a new pull request"},
        {"name": "fork_repository", "description": "Fork a repository"},
        {"name": "create_branch", "description": "Create a new branch in a repository"},
        {"name": "list_commits", "description": "List commits in a branch"},
        {"name": "list_issues", "description": "List issues in a repository"},
        {"name": "update_issue", "description": "Update an existing issue"},
        {"name": "add_issue_comment", "description": "Add a comment to an issue"},
        {"name": "search_code", "description": "Search for code across GitHub repositories"},
        {"name": "search_issues", "description": "Search for issues and pull requests"},
        {"name": "search_users", "description": "Search for GitHub users"},
        {"name": "get_issue", "description": "Get details of a specific issue"},
        {"name": "get_pull_request", "description": "Get details of a specific pull request"},
        {"name": "list_branches", "description": "List branches in a repository"}
    ]'::jsonb,
    ARRAY['development', 'devops'],
    ARRAY['github', 'git', 'repositories', 'issues', 'pull-requests', 'ci-cd'],
    'https://github.com/modelcontextprotocol/servers/tree/main/src/github',
    'MIT',
    FALSE, NULL
) ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 4. PostgreSQL (community)
-- ============================================================
INSERT INTO mcp_registry (
    name, display_name, description, author,
    version, endpoint_url, transport, tools_count, tools_list,
    categories, tags, repo_url, license,
    verified, security_score
) VALUES (
    'postgres',
    'PostgreSQL',
    'Community MCP server for PostgreSQL database interaction. Run read-only SQL queries, list tables, describe schemas, and explore your database safely through MCP.',
    'Community',
    '0.6.2',
    'npx:@modelcontextprotocol/server-postgres',
    'stdio',
    4,
    '[
        {"name": "query", "description": "Run a read-only SQL query against the connected database"},
        {"name": "list_tables", "description": "List all tables in the connected database"},
        {"name": "describe_table", "description": "Get the schema for a specific table"},
        {"name": "list_schemas", "description": "List all schemas in the connected database"}
    ]'::jsonb,
    ARRAY['data', 'development'],
    ARRAY['postgres', 'postgresql', 'database', 'sql', 'query'],
    'https://github.com/modelcontextprotocol/servers/tree/main/src/postgres',
    'MIT',
    FALSE, NULL
) ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 5. Slack (community)
-- ============================================================
INSERT INTO mcp_registry (
    name, display_name, description, author,
    version, endpoint_url, transport, tools_count, tools_list,
    categories, tags, repo_url, license,
    verified, security_score
) VALUES (
    'slack',
    'Slack',
    'Community MCP server for Slack workspace interaction. Send messages, manage channels, search messages, and interact with your Slack workspace through MCP.',
    'Community',
    '0.6.2',
    'npx:@modelcontextprotocol/server-slack',
    'stdio',
    8,
    '[
        {"name": "send_message", "description": "Send a message to a Slack channel"},
        {"name": "list_channels", "description": "List available Slack channels"},
        {"name": "search_messages", "description": "Search messages in Slack"},
        {"name": "get_channel_history", "description": "Get recent messages from a channel"},
        {"name": "get_thread_replies", "description": "Get replies in a thread"},
        {"name": "add_reaction", "description": "Add a reaction emoji to a message"},
        {"name": "get_users", "description": "List users in the workspace"},
        {"name": "get_user_profile", "description": "Get profile details for a user"}
    ]'::jsonb,
    ARRAY['communication', 'productivity'],
    ARRAY['slack', 'messaging', 'chat', 'team', 'communication'],
    'https://github.com/modelcontextprotocol/servers/tree/main/src/slack',
    'MIT',
    FALSE, NULL
) ON CONFLICT (name) DO NOTHING;

-- Ensure permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO mcp_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO mcp_user;
