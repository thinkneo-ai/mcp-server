# Chaos Engineering — Baseline Report

**Date:** 2026-04-26
**Version:** v3.12.0
**Infrastructure:** 5 containers (gateway, PostgreSQL 16, Redis 7, toxiproxy 2.9.0, WireMock 3.5.4)
**Total duration:** 5m07s
**Result:** 27/27 PASSED

## Test Matrix

| # | Scenario | Tests | Status | Duration |
|---|----------|-------|--------|----------|
| 1 | PostgreSQL down | 7 | 7/7 PASS | ~120s |
| 2 | Redis down | 5 | 5/5 PASS | ~40s |
| 3 | Provider timeout (30s latency) | 5 | 5/5 PASS | ~15s |
| 4 | Provider 429 rate limit | 5 | 5/5 PASS | ~10s |
| 5 | High latency (5s) | 5 | 5/5 PASS | ~20s |
| **Total** | | **27** | **27/27** | **307s** |

## Key Findings

### Scenario 1: PostgreSQL Down
- **Setup:** `docker stop thinkneo-chaos-postgres`
- **Pure-logic tools:** Work perfectly — thinkneo_check returns valid JSON
- **DB-dependent tools:** Return MCP error content or timeout (pool blocks)
- **Gateway stability:** PID unchanged through outage, no crash
- **Recovery:** Auto-reconnects within 15s after PG restart, no manual intervention

### Scenario 2: Redis Down
- **Setup:** `docker stop thinkneo-chaos-redis`
- **Behavior:** Fail-open — all 20 burst requests succeed (rate limiting disabled)
- **Gateway stability:** Running, no crash
- **Recovery:** Rate limiting resumes within 5s after Redis restart

### Scenario 3: Provider Timeout
- **Setup:** toxiproxy 30,000ms latency on provider proxy
- **Pure-logic tools:** thinkneo_check < 10s (unaffected by proxy)
- **Provider status:** < 5s (static data, no proxy path)
- **Simulate savings:** < 5s (local computation)
- **Recovery:** Immediate after toxic removal

### Scenario 4: Provider 429
- **Setup:** WireMock returns 429 with Retry-After: 5
- **Behavior:** Gateway handles gracefully, no infinite retry loops
- **10 rapid requests:** All complete within 30s
- **Recovery:** Normal service resumes after stub switches to 200

### Scenario 5: High Latency
- **Setup:** toxiproxy 5,000ms latency on provider proxy
- **P95 for pure tools:** 271ms (threshold: 2,000ms) — well within SLA
- **Concurrent requests:** 10/10 parallel requests all complete
- **No hangs:** Single requests complete within 30s
- **Recovery:** Latency returns to normal immediately after toxic removal

## Metrics

| Metric | Value |
|--------|-------|
| Stack boot time | ~10s (Docker build cached) |
| Total test duration | 307s (5m07s) |
| Gateway restarts | 0 |
| P95 latency (pure tools) | 271ms |

## Schedule

- **CI:** Every Sunday 03:00 UTC (`chaos.yml`)
- **Manual:** `workflow_dispatch` trigger available
- **Runbook:** See [runbook.md](runbook.md)
