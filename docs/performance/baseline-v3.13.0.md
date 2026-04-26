# Performance Baseline — v3.13.0

**Date:** 2026-04-26
**Environment:** Python 3.12, Linux 6.8.0 (amd64), mocked DB (isolates tool logic)
**Tests:** 26 benchmarks across 6 critical paths

## Summary

| Path | Target | Actual | Status |
|------|--------|--------|--------|
| Safety hot path (thinkneo_check) | P99 < 50ms | P99 = 16ms | PASS |
| Tool dispatch (no I/O) | P99 < 20ms | P99 = 4ms | PASS |
| Audit log write | > 300 ops/s | 417-523 ops/s | PASS |
| Cache hit/miss | P95 < 50ms | P95 = 2-3ms | PASS |
| SIEM export 10K events | < 5s | 5-33ms | PASS |
| Log redaction | > 5000 ops/s | 23,217 ops/s | PASS |

## Detailed Results

### Safety Tool (thinkneo_check)

| Scenario | P50 | P99 | Throughput |
|----------|-----|-----|------------|
| Short text (30 chars) | 0.7ms | 16.1ms | 1,161 ops/s |
| Long text (10K chars) | 13.2ms | 16.7ms | — |
| Max text (50K chars) | 56.0ms | 91.9ms | — |
| Injection detection | 0.8ms | 1.3ms | — |
| PII detection | 0.8ms | 1.2ms | — |

### Tool Dispatch (pure logic, no DB/network)

| Tool | P50 | P99 |
|------|-----|-----|
| provider_status | 0.9ms | 1.5ms |
| simulate_savings | 1.1ms | 1.8ms |
| compare_models | 1.5ms | 2.3ms |
| estimate_tokens | 2.9ms | 4.0ms |
| optimize_prompt | 0.6ms | 5.7ms |
| detect_injection | 0.3ms | 12.1ms |
| scan_secrets | 0.2ms | 8.3ms |

### Audit Log Throughput (mocked DB)

| Tool | Ops/s |
|------|-------|
| thinkneo_usage | 417 |
| thinkneo_log_risk_avoidance | 472 |
| thinkneo_log_decision | 523 |

### Cache Path (mocked DB)

| Operation | P50 | P95 |
|-----------|-----|-----|
| Cache miss (lookup) | 1.6ms | 2.3ms |
| Cache store | 1.6ms | 3ms |
| Cache stats | 1.3ms | 2.4ms |

### SIEM Export (10,000 events)

| Format | Duration | Output Size |
|--------|----------|-------------|
| JSON | 33ms | 1,597 KB |
| CSV | 10ms | 718 KB |
| CEF | 7ms | 856 KB |
| Syslog | 6ms | 1,044 KB |
| LEEF | 6ms | 868 KB |

### Log Redaction

| Scenario | Result |
|----------|--------|
| Short PII text throughput | 23,217 ops/s |
| 10K text with PII (P99) | 10.0ms |

## Regression Thresholds

If P99 degrades >20% from these baselines in CI, the perf job will fail:

| Metric | Baseline | Fail threshold |
|--------|----------|----------------|
| check short P99 | 16ms | 19ms |
| dispatch P99 (avg) | 4ms | 5ms |
| audit throughput | 417 ops/s | 334 ops/s |
| SIEM JSON 10K | 33ms | 40ms |
| redaction throughput | 23,217 ops/s | 18,574 ops/s |
