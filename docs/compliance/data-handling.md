# Data Handling

## What We Collect

| Data Type | Stored Where | Retention | Purpose |
|-----------|-------------|-----------|---------|
| API key hash (SHA-256) | PostgreSQL | Until key deleted | Authentication |
| Tool call logs | PostgreSQL | 90 days | Usage tracking, billing |
| A2A interaction logs | PostgreSQL | 90 days | Audit trail |
| Memory files (.md) | Docker volume | Until user deletes | Project context |
| Session traces | PostgreSQL | 30 days | Observability |
| Rate limit events | PostgreSQL | 7 days | Rate enforcement |

## What We Do NOT Collect
- Prompt content (tool arguments are not logged)
- Model responses (not stored by the gateway)
- User passwords (keys are hashed, never stored in plaintext)
- IP addresses (not stored in usage_log; used transiently for rate limiting)

## Data Location
- Production: DigitalOcean NYC1 region (US)
- Self-hosted: wherever you deploy

## Deletion
- API keys: contact hello@thinkneo.ai
- Usage logs: auto-expire after 90 days
- Memory files: delete via thinkneo_write_memory or direct volume access

## Encryption
- In transit: TLS 1.3 (nginx termination)
- At rest: Host-level volume encryption (DigitalOcean managed)
- Key hashing: SHA-256 (one-way, not reversible)
