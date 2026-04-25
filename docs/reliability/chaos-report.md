# Chaos Engineering Report

> **ThinkNEO MCP+A2A Gateway**
> First run: pending (will be updated after first green CI run)
> Schedule: Weekly, Sunday 03:00 UTC

## Scenarios Tested

| # | Scenario | Fault Injection | Expected Behavior | Status |
|---|----------|----------------|-------------------|--------|
| 1 | PostgreSQL down | docker stop postgres | Public tools work, DB tools error gracefully, auto-recovery | Pending |
| 2 | Redis down | docker stop redis | Fail-open rate limiting, no crash, auto-recovery | Pending |
| 3 | Provider timeout | toxiproxy 30s latency | Timeout within 15s, no hang, other tools unaffected | Pending |
| 4 | Provider 429 | wiremock returns 429 | Handles gracefully, no infinite loop, isolation per key | Pending |
| 5 | High latency | toxiproxy 5s latency | P95 < 2s for pure tools, concurrent requests complete | Pending |

## Infrastructure

- Gateway: Docker container (port 18081)
- PostgreSQL: 16-alpine
- Redis: 7-alpine
- Toxiproxy: Shopify 2.9.0 (fault injection)
- WireMock: 3.5.4 (mock provider)

## Baseline Metrics

*Will be populated after first successful run.*

## Runbook

See [runbook.md](runbook.md) for operational procedures per scenario.
