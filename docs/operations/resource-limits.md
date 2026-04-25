# Container Resource Limits

> **Applied:** 2026-04-25
> **Server:** 161.35.12.205 (thinkneoDO) — 4 CPU, 16 GB RAM
> **Review cadence:** After 30 days of production data

## Current Limits

| Container | CPU | Memory | Reservation (CPU/Mem) | Rationale |
|-----------|-----|--------|----------------------|-----------|
| thinkneo-mcp-server | 2.0 | 2 GB | 0.25 / 128 MB | Primary API gateway, highest priority |
| n8n | 1.0 | 1 GB | 0.25 / 128 MB | Workflow engine, moderate usage |
| n8n-postgres | 1.0 | 1 GB | 0.25 / 128 MB | Database, shared across services |
| thinkneo-a2a-agent | 1.0 | 512 MB | 0.25 / 128 MB | A2A protocol handler |
| thinkneo-a2a-redis | 0.5 | 300 MB | 0.1 / 32 MB | A2A task state cache |
| thinkneo-robot-agent | 0.5 | 256 MB | 0.1 / 32 MB | Robot chat agent |
| thinkneo-robot-redis | 0.2 | 80 MB | 0.05 / 16 MB | Robot state cache |
| thinkneo-admin-api | 1.0 | 512 MB | 0.25 / 128 MB | Admin API |
| thinkneo-admin-ui | 1.0 | 512 MB | 0.25 / 128 MB | Admin dashboard |
| neo-brain-api | 1.0 | 512 MB | 0.25 / 128 MB | Brain/memory API |
| thinkauth-api | 1.0 | 512 MB | 0.25 / 128 MB | Auth service |
| thinkneo-voice-attendant | 1.0 | 512 MB | 0.25 / 128 MB | Twilio voice agent |
| thinkneo-finance-neocfo-api | 1.0 | 512 MB | 0.25 / 128 MB | NeoCFO finance API |
| thinkneo-finance-neobank-api | 1.0 | 512 MB | 0.25 / 128 MB | NeoBank finance API |
| thinkneo-finance-redis | 0.5 | 256 MB | 0.1 / 32 MB | Finance cache |
| v0-site | 1.0 | 512 MB | 0.25 / 128 MB | Main website |
| tenant-app | 1.0 | 512 MB | 0.25 / 128 MB | Tenant dashboard |
| thinkneo-app-staging-web | 1.0 | 2 GB | 0.25 / 128 MB | Staging (pre-existing) |
| thinkneo-email-templates-v0 | 1.0 | 512 MB | 0.25 / 128 MB | Email renderer |

**Total allocated (limits):** ~15.5 CPU / ~12 GB memory
**Server capacity:** 4 CPU / 16 GB RAM
**Overcommit ratio:** ~3.9x CPU, ~0.75x memory (safe — not all containers peak simultaneously)

## How Limits Were Applied

- **Compose-managed containers:** Limits in docker-compose.yml `deploy.resources`
- **Standalone containers:** Applied via `docker update --cpus --memory --memory-swap`
- **Swap:** Disabled per container (`memory-swap = memory`) to prevent OOM swap thrashing

## Monitoring

Check for OOM kills:
```bash
docker events --since 24h --filter event=oom
```

Check current usage vs limits:
```bash
docker stats --no-stream
```

## Review Plan

After 30 days of production:
1. Check `docker stats` peak usage over the period
2. Tighten limits for containers consistently using <50% of allocation
3. Increase limits for containers hitting >80% regularly
4. Consider dedicated Redis limits per actual data size
