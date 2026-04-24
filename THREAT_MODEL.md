# Threat Model — ThinkNEO MCP+A2A Gateway

> Last updated: 2026-04-25
> Scope: `mcp.thinkneo.ai` production deployment (59 MCP tools, 24 A2A skills)

---

## 1. Attack Surface

| Surface | Protocol | Exposure | Auth |
|---------|----------|----------|------|
| `/mcp` | MCP (Streamable HTTP, JSON-RPC 2.0) | Public internet | Bearer token (optional for public tools) |
| `/.well-known/agent.json` | A2A Agent Card | Public internet | None (discovery) |
| `/a2a` | A2A Protocol (JSON-RPC 2.0) | Public internet | Bearer token |
| `/mcp/docs` | HTML landing page | Public internet | None |
| `/registry` | HTML marketplace page | Public internet | None |
| `/mcp/signup` | Self-signup endpoint | Public internet | None |
| `/oauth/*` | OAuth 2.1 flows | Public internet | Client credentials |
| `/guardian/health` | Health check | Public internet | None |
| PostgreSQL (port 5432) | TCP | Docker bridge only (172.17.0.1) | Password |
| Memory volume (`/app/memory`) | Filesystem | Container only | Container UID |

## 2. Threat Actors

| Actor | Access Level | Motivation | Capability |
|-------|-------------|------------|------------|
| **Unauthenticated internet** | Public tools only | Abuse free tier, injection, data exfil | Can call ~10 public tools, attempt SSRF via registry_publish |
| **Authenticated free-tier** | All tools, 500 calls/month | Exceed limits, privilege escalation | Has API key (auto-provisioned), can call all 59 tools |
| **Authenticated enterprise** | All tools, unlimited | Data exfiltration from other tenants | Trusted key, but multi-tenant isolation matters |
| **Malicious MCP client** | Full MCP protocol | Exploit protocol edge cases | Can send malformed JSON-RPC, oversized payloads |
| **Malicious A2A agent** | Full A2A protocol | Exploit bridge, task injection | Can submit crafted A2A tasks that get translated to MCP calls |

## 3. STRIDE Analysis

### Spoofing

| Threat | Component | Mitigation | Status |
|--------|-----------|------------|--------|
| Forge API key | Auth middleware | SHA-256 hashed keys, no plaintext storage | Mitigated |
| Replay Bearer token | Auth middleware | Stateless HTTP (no session to hijack), HTTPS enforced by nginx | Mitigated |
| Impersonate another tenant | Database | Queries scoped by `key_hash` — each key sees only own data | Mitigated |
| OAuth client spoofing | OAuth middleware | Client secret validation, PKCE supported | Mitigated |

### Tampering

| Threat | Component | Mitigation | Status |
|--------|-----------|------------|--------|
| Modify memory files | write_memory tool | Auth required, filename regex validation, path traversal guard (resolve + startswith) | Mitigated |
| SQL injection | DB-touching tools | Parameterized queries (`%s` placeholders), `validate_workspace()` sanitizer | Mitigated |
| Modify marketplace packages | registry_publish | `owner_key_hash` ownership check on update | Mitigated |
| Tamper with accountability chain | A2A governance | SHA-256 hash-linked chain, immutable append-only records | Mitigated |

### Repudiation

| Threat | Component | Mitigation | Status |
|--------|-----------|------------|--------|
| Deny tool usage | usage_log | Every call logged with key_hash, tool_name, timestamp, cost | Mitigated |
| Deny A2A interaction | a2a_interactions table | Full audit trail with from_agent, to_agent, action, payload | Mitigated |
| Deny claim outcome | outcome_claims table | Claims are immutable once registered, verification recorded | Mitigated |

### Information Disclosure

| Threat | Component | Mitigation | Status |
|--------|-----------|------------|--------|
| Read other tenant's data | All DB tools | Queries always filtered by `key_hash` | Mitigated |
| Path traversal on memory | read_memory, write_memory | `Path.resolve()` + `startswith(_MEMORY_DIR)` guard | Mitigated |
| Leak API keys in responses | All tools | Keys stored as SHA-256 hash, only `key_prefix` (8 chars) shown | Mitigated |
| PII in tool responses | thinkneo_check | Detects PII but does not echo it back — returns metadata only | Mitigated |
| SSRF via marketplace publish | registry_publish | `_is_safe_url()` blocks private IPs, localhost, metadata endpoints, .internal domains | Mitigated |

### Denial of Service

| Threat | Component | Mitigation | Status |
|--------|-----------|------------|--------|
| Exhaust free-tier calls | Free-tier middleware | 500 calls/month hard limit, per-key enforcement | Mitigated |
| Exhaust DB connections | Connection pool | psycopg_pool with max_size=10, timeout=10s | Mitigated |
| Large payload | Tool input | `text[:50_000]` truncation in safety tools | Mitigated |
| Rate limiting bypass | Per-minute buckets | `rate_limit_events` table, configurable per key | Mitigated |
| Container resource exhaustion | Docker | Resource limits in docker-compose (if configured) | Partial — no explicit limits set |

### Elevation of Privilege

| Threat | Component | Mitigation | Status |
|--------|-----------|------------|--------|
| Free → Enterprise tier | Free-tier middleware | Tier stored in DB, checked on every call, no client-side trust | Mitigated |
| Free → Pro tool access | Plan enforcement | `require_plan()` checks DB plan column before tool execution | Mitigated |
| Unauthenticated → authenticated | Auth middleware | `require_auth()` raises ValueError, caught by MCP framework | Mitigated |
| Key rotation bypass | revoked_keys table | `is_key_revoked()` checked before key acceptance | Mitigated |

## 4. Residual Risks

| Risk | Severity | Rationale |
|------|----------|-----------|
| Dynamic WHERE clauses flagged by SAST | Low | Conditions use `%s` parameterization — safe but pattern triggers scanner false positives. Documented with inline comments. |
| No Docker resource limits | Medium | Container has no explicit CPU/memory limits in docker-compose. Mitigated by DO droplet limits but not defense-in-depth. |
| Regex-based injection detection | Medium | Guardrail uses 10 regex patterns — evadable by encoding, multilingual, or novel attack patterns. ML-based detection planned for Enterprise tier. |
| Memory volume writable | Low | `/app/memory` mounted `:rw` — container can write to host filesystem within that directory. Limited by path validation to `.md` files only. |
| Hardcoded model pricing | Low | Smart Router uses static pricing data that may become stale. Updated manually per release. |

## 5. Security Controls Summary

| Control | Implementation |
|---------|---------------|
| Authentication | Bearer token via ContextVar, OAuth 2.1 |
| Authorization | Tier-based (free/pro/enterprise), plan gates, scopes |
| Input validation | Pydantic Field validators, workspace regex, filename regex |
| Output sanitization | JSON-only responses, no HTML injection surface |
| SQL injection prevention | Parameterized queries (`%s`), `validate_workspace()` |
| Path traversal prevention | `Path.resolve()` + `startswith()` guard |
| SSRF prevention | `_is_safe_url()` with ipaddress + urlparse validation |
| Rate limiting | Per-minute buckets in DB, configurable per key |
| Audit logging | Every tool call logged to `usage_log` with cost estimate |
| Key management | SHA-256 hashing, rotation support, revocation table |
| HTTPS | Enforced by nginx reverse proxy (TLS termination) |
| CORS | Explicit allowlist (no wildcard with credentials) |
