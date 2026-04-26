# Reliability Runbook — ThinkNEO MCP Gateway

Production remediation procedures for each failure scenario validated by chaos engineering tests.

---

## Scenario 1: PostgreSQL Down

**Symptom:** DB-dependent tools (check_spend, usage, set_baseline, etc.) return errors. Usage logging stops. Public tools continue working.

**Impact:** Authenticated tools degraded; public tools unaffected. Auth still works (ContextVar-based, no DB call).

**Action:**
1. Check PG container: `docker ps | grep postgres`
2. If stopped: `docker start thinkneo-mcp-postgres`
3. If crashed: check `docker logs thinkneo-mcp-postgres` for OOM/disk full
4. Gateway auto-reconnects via connection pool — **no restart needed**
5. Verify recovery: call a DB tool, confirm 200

**Recovery time:** ~15s after PG restarts (pool reconnect)

**Prevention:** Monitor PG health via `pg_isready` health check. Alert on 3 consecutive failures.

---

## Scenario 2: Redis Down

**Symptom:** Rate limiting stops enforcing. Burst traffic not throttled.

**Impact:** Requests still processed (fail-open design). Risk of abuse during gap.

**Action:**
1. Restart Redis: `docker start thinkneo-mcp-redis`
2. Verify: `docker exec thinkneo-mcp-redis redis-cli ping`
3. Monitor for burst abuse during downtime window
4. Review usage_log for anomalous patterns during gap

**Recovery time:** ~5s after Redis restarts

**Prevention:** Redis health check in docker-compose. Consider Sentinel or cluster for HA.

---

## Scenario 3: Provider Timeout

**Symptom:** Slow tool responses from provider-dependent tools. Customer complaints about latency.

**Impact:** Tools that proxy to external providers timeout. Pure-logic tools (thinkneo_check, provider_status, simulate_savings) unaffected.

**Action:**
1. Check provider status page (status.anthropic.com, status.openai.com)
2. If provider issue: wait or switch to fallback model via Smart Router
3. If network issue: check DO networking, DNS resolution
4. Increase timeout temporarily if transient
5. Verify recovery: call affected tool, confirm normal latency

**Recovery time:** Automatic once provider latency resolves

**Prevention:** Multi-provider Smart Router with automatic fallback. P95 alerting via OTEL.

---

## Scenario 4: Provider Rate Limit (429)

**Symptom:** Tool calls failing with rate limit errors from upstream provider.

**Impact:** Affected provider's models unavailable. Other providers and pure-logic tools unaffected.

**Action:**
1. Reduce request volume to affected provider
2. Smart Router auto-falls back to next provider in priority list
3. Contact provider for limit increase (long-term)
4. Enable request queuing if not already active
5. Check if rate limit is per-key or per-org at provider side

**Recovery time:** Typically 5-60s (per provider's Retry-After header)

**Prevention:** Per-provider rate limit tracking. Multiple API keys per provider.

---

## Scenario 5: High Latency

**Symptom:** P95 response times above SLA target. Gradual degradation, not outage.

**Impact:** Customer experience degrades. OTEL metrics show elevated latency.

**Action:**
1. Identify source: check OTEL traces for slow spans
2. If provider: switch to faster model (e.g., Haiku instead of Sonnet)
3. If DB: check PG query performance, connection pool utilization
4. If network: check DO bandwidth/routing
5. Consider request shedding for lowest-priority tiers

**Recovery time:** Automatic once underlying latency resolves

**Prevention:** P95 alerting. Connection pooling tuned. Multi-region deployment.

---

## General Guidelines

- **Gateway auto-recovers** from all tested scenarios — no restart needed
- **Public tools** (thinkneo_check, provider_status, simulate_savings) are always available
- **Redis** fails open — rate limiting disabled but service continues
- **PostgreSQL** failure isolates to DB-dependent tools only
- Run `pytest tests/chaos/ -v` locally to validate recovery after infrastructure changes

## Escalation

1. On-call engineer investigates using this runbook
2. If unresolved in 15 minutes: escalate to @dudu-manager
3. If customer-facing impact > 30 minutes: create incident in Linear
4. Post-incident: update chaos tests if new failure mode discovered
