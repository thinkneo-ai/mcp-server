# Changelog

All notable changes to the ThinkNEO MCP Server.

## [1.28.0] — 2026-04-26 — Complete MCP Spec Compliance

### Added
- **logging capability** (MCP spec 2024-11-05): server-side log level control via `logging/setLevel`, server-initiated log notifications with level filtering, per-session isolation, full audit trail of level changes. 8 dedicated tests.
- **completions capability** (MCP spec 2024-11-05): autocomplete for prompt arguments via `completion/complete`. Workspace name completion (auth-scoped, anonymous returns empty for privacy), provider list (Anthropic, OpenAI, Google, Mistral, NVIDIA), provider-aware model list completion across all 5 providers. 12 dedicated tests.

### Validated
- **All 6 MCP capabilities** declared and operational in production: tools, resources, prompts, logging, completions, experimental.
- **Protocol version negotiation**: server accepts 2024-11-05 AND 2025-03-26 client versions, with proper downgrade for unsupported versions.
- **External validation**: all 6 spec methods (initialize, tools/list, resources/list, prompts/list, logging/setLevel, completion/complete) pass against production.
- **Error case validation**: invalid log levels return -32602, nonexistent prompts return empty values, anonymous workspace completions return empty (privacy by default).

### Result
ThinkNEO MCP now implements 100% of the Model Context Protocol 2024-11-05 specification, with forward compatibility to 2025-03-26:
- 62 tools (with destructiveHint, readOnlyHint, idempotentHint, openWorldHint annotations on all)
- 2 resources
- 2 prompts (with completions)
- logging capability
- completions capability
- experimental capability slot

Test suite: 452 passing, 5 xfailed, 0 failures.

## [1.27.0] — 2026-04-25 — Enterprise E2E Audit Fixes

### Security
- Removed auto-registration of arbitrary Bearer tokens (SEC-01)
- Added IP-based rate limiting for anonymous public tool access (30/hour)
- Added connection pooling (psycopg_pool, min=2/max=20)
- Added circuit breaker for fail-fast on DB outages
- Added XSS and shell command injection detection (6 patterns)
- Expanded guardrail detection from 76% to 95% corpus pass rate
- Fixed Finance Redis requirepass, .env permissions, audit log triggers
- Added Docker resource limits on all 19 containers
- Migrated 3 Redis containers to non-root (user 999:999)

### Operations
- Daily PostgreSQL backup (host + Docker) with 30-day retention
- Weekly automated backup restore test (RTO: 86s, RPO: <24h)
- Disk usage monitoring (hourly, alert at 80%)
- Cleanup cron for orphan API keys (dryrun mode)

### Compliance
- Published sub-processor list (docs/compliance/sub-processors.md)
- Added DPA template (docs/compliance/DPA_TEMPLATE.md)
- Added tool annotations (destructiveHint, openWorldHint) on all 62 tools
- Fixed HSTS consistency, agent card redirect, key prefix standardization

### Documentation
- Full E2E audit report suite (6 documents in docs/audit/)
- 29 findings: 24 resolved, 2 partial, 2 deferred, 1 accepted
