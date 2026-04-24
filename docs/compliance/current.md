# Compliance — Current Posture

> Last updated: 2026-04-25

## What Exists Today

### Security Controls
- **SAST**: bandit + pip-audit in CI, 0 HIGH/CRITICAL findings
- **Secrets scanning**: Git history scanned, .env not tracked
- **Input validation**: Parameterized SQL, SSRF protection, path traversal guards
- **Authentication**: Bearer token + OAuth 2.1, SHA-256 key hashing
- **Authorization**: Tier-based (free/pro/enterprise), plan gates, scopes
- **Encryption in transit**: TLS 1.3 via nginx reverse proxy
- **Encryption at rest**: PostgreSQL on encrypted Docker volumes (host-level)
- **Audit trail**: Every tool call logged (key_hash, tool, timestamp, cost)
- **Rate limiting**: Per-key burst + per-minute enforcement
- **Log redaction**: PII and secrets auto-scrubbed (12 patterns)

### Security Documentation
- [THREAT_MODEL.md](../../THREAT_MODEL.md) — STRIDE analysis
- [SECURITY.md](../../SECURITY.md) — Vulnerability reporting policy
- [AUDIT_REPORT.md](../../AUDIT_REPORT.md) — Test results
- [TCK_REPORT.md](../../TCK_REPORT.md) — A2A protocol compliance

### Access Control
- API keys auto-provisioned via self-signup (500 calls/month free)
- Master key for internal tools (env var, not in code)
- Key rotation supported with revocation log
- IP allowlist per key (optional)

## What We Do NOT Have Yet
- SOC 2 Type I certification (see roadmap)
- ISO 27001 certification
- Formal penetration test report from third party
- BAA for HIPAA-covered entities
- Data Processing Agreement template (DPA)
