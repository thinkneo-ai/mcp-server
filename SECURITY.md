# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in ThinkNEO MCP Gateway, please report it responsibly:

**Email:** security@thinkneo.ai
**Response time:** Within 48 hours
**PGP key:** Available on request

### What to include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### What to expect:
1. Acknowledgment within 48 hours
2. Assessment and triage within 5 business days
3. Fix timeline communicated within 10 business days
4. Credit in release notes (unless you prefer anonymity)

## Scope

In scope:
- ThinkShield detection engine, rule packs, and middleware
- MCP tools and protocol implementation
- A2A skills and protocol implementation
- MCP endpoint (mcp.thinkneo.ai/mcp)
- A2A endpoint (agent.thinkneo.ai/a2a)
- Authentication and authorization
- Data handling and storage
- API key management

Out of scope:
- Proprietary ThinkNEO Platform components (thinkneo.ai infrastructure)
- Social engineering
- DDoS attacks
- Issues in third-party dependencies (report to the upstream project)

## Security Measures

See [THREAT_MODEL.md](THREAT_MODEL.md) for the full STRIDE analysis.

### Current Controls
- SAST: bandit (0 HIGH findings), pip-audit (0 CRITICAL)
- Auth: Bearer token + OAuth 2.1, API key hashing (SHA-256)
- Input: Parameterized SQL, path traversal guards, SSRF protection
- Rate limiting: Per-key burst + per-minute limits
- Audit: Every tool call logged with timestamp, key hash, cost
- Encryption: TLS 1.3 (nginx termination), PostgreSQL on Docker bridge
- PII: Automatic log redaction (12 patterns)

### Compliance Roadmap
See [docs/compliance/](docs/compliance/) for current posture and roadmap.

## Hall of Fame

We gratefully acknowledge security researchers who have responsibly disclosed vulnerabilities to ThinkNEO. Thank you for helping keep our users safe.

| Researcher | Date | Summary |
|------------|------|---------|
| *Be the first!* | — | Report a vulnerability to [security@thinkneo.ai](mailto:security@thinkneo.ai) |
