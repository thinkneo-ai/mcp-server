# Gap Analysis — Test Suite vs Original Plan

> Generated: 2026-04-25
> pytest collect: **310 test nodes** (target: 1,087)
> Line coverage: **40%** (target: ≥85%)
> Delta: **777 tests missing**

---

## FASE 2 — Unit Tests

```
Plan: 300 tests
Delivered: 141 tests
Delta: -159 tests
```

| Category | Plan | Delivered | Gap | Detail |
|----------|------|-----------|-----|--------|
| Safety tools deep | 60 | 27 | -33 | Missing: boundary per-pattern, multi-PII combos, encoding edge cases, max-length per pattern |
| Memory tools | 20 | 11 | -9 | Missing: symlink, concurrent write, large file, unicode filenames, MEMORY.md edge cases |
| Governance (6 tools) | 30 | ~14 (generic) | -16 | Missing: each tool with workspace validation, period parsing, group_by, custom dates, empty results |
| Router | 20 | 9 | -11 | Missing: each model explicitly, preferred_providers, blocked_providers, budget_per_request, text_sample |
| Trust Score | 15 | ~4 (generic) | -11 | Missing: score dimension breakdown, badge token format, org_name validation, repeat evaluation |
| Generic wrappers (42 tools) | 155 | 76 (generic) | -79 | Missing: boundary per tool (empty input, oversized, null), error path per tool, idempotence checks |

**Motivo do delta:** Used parametrized classes (`TestAuthToolsReturnJSON`, `TestAuthToolsRejectUnauthenticated`) that generate multiple test nodes but only test JSON validity + auth rejection. Missing: boundary, error path, idempotence, state isolation per tool. Several DB-heavy tools (SLA, policy_engine, observability, outcome_validation) were excluded because mock_db returns None and tools crash on `None["field"]`.

**Correction plan:** Add per-tool boundary/error tests. For DB-heavy tools, configure mock_cursor.fetchone to return realistic dicts. Add dedicated test files for trust_score, governance, and each excluded tool category.

---

## FASE 3 — Adversarial Tests

```
Plan: 472 tests
Delivered: 102 test nodes (78 pass + 24 xfail) + 4 hypothesis strategies = 106 nodes
Delta: -366 tests
```

| Category | Plan | Delivered | Gap |
|----------|------|-----------|-----|
| Injection corpus × 2 tools | 300 | 65 (1 tool only) | -235 |
| Negative controls × 2 tools | 62 | 31 (1 tool only) | -31 |
| Advanced cases | 73 | 0 | -73 |
| Property-based strategies | 37 | 4 | -33 |

**Motivo do delta:** Only tested against `thinkneo_check`, not `thinkneo_detect_injection`. Missing the duplicate test set for the second tool. Advanced cases (payload splitting, multi-turn, context manipulation, delimiter injection, encoded payloads, unicode) not implemented at all. Property-based only has 4 strategies instead of 37. The 24 xfails have no GitHub issues linked.

**Correction plan:** Duplicate all corpus tests to also run against `thinkneo_detect_injection`. Add 73 advanced payload tests. Add 33 more hypothesis strategies. Create GitHub issues for 24 xfails.

---

## FASE 4 — Security Tests

```
Plan: 175 tests
Delivered: 52 tests
Delta: -123 tests
```

| Category | Plan | Delivered | Gap |
|----------|------|-----------|-----|
| SQL injection (10 payloads × 10 tools) | 100 | 18 (6×3) | -82 |
| Path traversal (12 × 2 tools) | 24 | 16 (8×2) | -8 |
| SSRF (11 URLs + 1 safe) | 12 | 12 | 0 |
| Auth bypass | 15 | 6 | -9 |
| Input validation | 25 | 0 | -25 |

**Motivo do delta:** SQL injection only tested 3 workspace-based tools (check_spend, evaluate_guardrail, check_policy) instead of all 10 DB-touching tools. Path traversal missing 4 payloads. Auth bypass missing: expired token, revoked key, malformed bearer, SQL-in-token, whitespace-padded token, case sensitivity. Input validation (null bytes, oversized, type confusion, unicode normalization, control chars) not implemented at all.

**Correction plan:** Expand SQLi to all 10 DB-touching tools. Add 4 path traversal payloads. Add 9 auth bypass cases. Create 25 input validation tests.

---

## FASE 5 — Integration + Performance + Regression

```
Plan: 140 tests
Delivered: 15 tests
Delta: -125 tests
```

| Category | Plan | Delivered | Gap |
|----------|------|-----------|-----|
| Integration (MCP protocol) | 12 | 0 | -12 |
| Integration (middleware stack) | 15 | 0 | -15 |
| Integration (free-tier lifecycle) | 8 | 0 | -8 |
| Performance (safety P99) | 8 | 3 | -5 |
| Performance (other P99) | 17 | 2 | -15 |
| Regression (per-tool JSON) | 59 | 6 (sampled) | -53 |
| Regression (inventory + annotations) | 21 | 4 | -17 |

**Motivo do delta:** No integration tests at all (would need ASGI TestClient, skipped entirely). Performance only tested 5 tools instead of 25. Regression tests used parametrized sampling instead of individual per-tool test nodes. No per-tool `test_tool_X_returns_json` functions.

**Correction plan:** Implement ASGI TestClient integration tests. Expand performance to all tool categories. Generate 59 individual regression test functions (one per tool). Add middleware tests.

---

## Coverage Analysis

```
Current: 40% line coverage (target: ≥85%)
Files at 0%: 12 files (completely untested)
```

| File | Coverage | Status |
|------|----------|--------|
| src/agent_card.py | 0% | No tests |
| src/badge.py | 0% | No tests |
| src/capabilities.py | 0% | No tests |
| src/landing.py | 0% | No tests |
| src/oauth.py | 0% | No tests (426 lines) |
| src/registry_landing.py | 0% | No tests |
| src/server.py | 0% | No tests |
| src/signup.py | 0% | No tests (172 lines) |
| src/tool_logger.py | 0% | No tests |
| src/tools/compare_models.py | 0% | No tests |
| src/tools/injection.py | 0% | No tests |
| src/tools/optimize_prompt.py | 0% | No tests |
| src/tools/pii_intl.py | 0% | No tests |
| src/tools/secrets.py | 0% | No tests |
| src/agent_sla.py | 11% | Minimal |
| src/compliance_export.py | 13% | Minimal |
| src/observability.py | 11% | Minimal |
| src/outcome_validation.py | 11% | Minimal |
| src/security.py | 22% | Minimal |

**Critical gaps for 85% target:** oauth.py (426 lines at 0%), signup.py (172 lines at 0%), server.py (56 lines at 0%), a2a_bridge.py (265 lines at 46%). These 4 files alone represent ~920 uncovered lines.

---

## Summary

| Phase | Plan | Delivered | Gap | % Delivered |
|-------|------|-----------|-----|-------------|
| 2 — Unit | 300 | 141 | -159 | 47% |
| 3 — Adversarial | 472 | 106 | -366 | 22% |
| 4 — Security | 175 | 52 | -123 | 30% |
| 5 — Integ+Perf+Regr | 140 | 15 | -125 | 11% |
| **Total** | **1,087** | **310** | **-777** | **29%** |

---

## Time Estimate for Correction

| Task | Tests to add | Estimated days |
|------|-------------|----------------|
| Fase 2 completion (159 tests) | 159 | 2 |
| Fase 3 completion (366 tests) | 366 | 2 |
| Fase 4 completion (123 tests) | 123 | 1 |
| Fase 5 completion (125 tests) | 125 | 2 |
| Coverage gap (0% files) | ~100 additional | 1 |
| xfail issues + AUDIT update | documentation | 0.5 |
| CI gate + v3.1.0 release | infra | 0.5 |
| **Total** | **~877 tests** | **9 days** |

**Deadline: 5 maio. Available: 10 days (25 abr — 4 mai). Fits with 1 day buffer.**
