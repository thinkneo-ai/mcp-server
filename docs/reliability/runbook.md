# Reliability Runbook

Operational procedures for each chaos-tested failure scenario.

## Scenario 1: PostgreSQL Down

**Symptom:** DB-dependent tools (check_spend, set_baseline, etc.) return errors. Usage logging stops.

**Impact:** Public tools (thinkneo_check, provider_status, simulate_savings) continue working. Auth still works (ContextVar-based, no DB call).

**Action:**
1. Check PG container: `docker ps | grep postgres`
2. If stopped: `docker start thinkneo-chaos-postgres` (or production equivalent)
3. If crashed: check `docker logs` for OOM/disk full
4. Gateway auto-reconnects — no restart needed
5. Verify recovery: call a DB tool, confirm 200

**Prevention:** Monitor PG health via `pg_isready` health check. Alert on 3 consecutive failures.

## Scenario 2: Redis Down

**Symptom:** Rate limiting stops enforcing. Burst traffic not throttled.

**Impact:** Requests still processed (fail-open). Risk of abuse during gap.

**Action:**
1. Restart: `docker start <redis-container>`
2. Monitor for burst abuse during downtime window
3. Verify rate limiting works: send 100 rapid requests, confirm 429 after limit
4. Review usage_log for anomalous patterns during gap

**Prevention:** Redis health check in docker-compose. Sentinel or cluster for HA.

## Scenario 3: Provider Timeout

**Symptom:** Slow tool responses. Customer complaints about latency.

**Impact:** Tools that proxy to external providers (bridge_a2a_to_mcp) timeout. Pure-logic tools unaffected.

**Action:**
1. Check provider status page (status.anthropic.com, status.openai.com)
2. If provider issue: wait or switch to fallback model in Smart Router config
3. If network issue: check DO networking, DNS resolution
4. Increase timeout temporarily if transient: `TOOL_TIMEOUT=30` in .env
5. Verify recovery: call affected tool, confirm normal latency

**Prevention:** Multi-provider Smart Router with automatic fallback. P95 alerting via OTEL.

## Scenario 4: Provider Rate Limit (429)

**Symptom:** Tool calls failing with rate limit errors from upstream provider.

**Impact:** Affected provider's models unavailable. Other providers unaffected.

**Action:**
1. Automatic: Smart Router fallback to next provider in priority list (already configured)
2. Reduce request volume per affected API key
3. Contact provider for limit increase (long-term)
4. Enable request queuing if not already active
5. Check if rate limit is per-key or per-org at provider side

**Prevention:** Per-provider rate limit tracking. Request queuing with backpressure. Multiple API keys per provider.

## Scenario 5: High Latency

**Symptom:** P95 > SLA target. Gradual degradation, not outage.

**Impact:** Customer experience degrades. OTEL metrics show elevated latency.

**Action:**
1. Identify source: check OTEL traces for slow spans
2. If provider: switch to faster model (e.g., Haiku instead of Sonnet)
3. If DB: check PG query performance, connection pool utilization
4. If network: check DO bandwidth, consider CDN or edge deployment
5. Consider request shedding for lowest-priority tiers

**Prevention:** P95 alerting. Multi-region deployment. Connection pooling tuned.
