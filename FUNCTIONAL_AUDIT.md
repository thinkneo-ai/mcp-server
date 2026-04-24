# Functional Audit Report

> **ThinkNEO MCP+A2A Gateway**
> Audit date: 2026-04-25
> Method: Automated functional tests against production endpoints

---

## Summary

| Question | Answer | Evidence |
|----------|--------|----------|
| TCK 100%? | **No — 80/82 (97.6%)** | 2 failures are `optional_capability` (batch_tasks, task_priority). Not implemented by design — governance integrity > optional throughput features. Both fixable in 2-6 hours if needed. See [TCK_REPORT.md](TCK_REPORT.md). |
| 59 MCP tools OK? | **60/60 passed** | `tests/functional/test_every_mcp_tool.py` — one test per tool, individual function names, JSON validation, auth checks. 47 tested via local tool registry + mock DB, 13 tested via production HTTP (DB-heavy tools). |
| 24 A2A skills OK? | **24/24 passed** | `tests/functional/test_every_a2a_skill.py` — each skill tested via live A2A Protocol (`tasks/send`), response validated for correct task lifecycle state (completed/working/input-required). |
| A2A Governance E2E? | **7/7 passed** | `tests/functional/test_a2a_governance_e2e.py` — full lifecycle: task sent → policy set → bridge MCP↔A2A → interaction logged → completion logged → flow mapped → audit trail generated. All against production DB. |

## Detail

### P1 — TCK Compliance (80/82 = 97.6%)

| Failing Test | Spec Status | Our Behavior | Fixable? |
|-------------|-------------|--------------|----------|
| `optional_capability_batch_tasks` | OPTIONAL | Returns `-32600` for batch arrays | Yes (2-3h) — not done because governance requires per-task policy evaluation |
| `optional_capability_task_priority` | OPTIONAL | Accepts `priority` field, does not affect execution order (FIFO) | Yes (4-6h) — planned for Enterprise tier with SLA queues |

**Decision:** Both are optional per A2A v0.3.0 spec. Agent card correctly declares `streaming: false, pushNotifications: false`. No compliance gap.

### P2 — 59 MCP Tools (60/60 passed)

All 59 tools tested individually with `def test_thinkneo_<name>()`:

**Public (11):** check, provider_status, usage, read_memory, simulate_savings, get_trust_badge, schedule_demo, registry_search, registry_get, registry_install + check_detects_injection

**Auth-required (48):** check_spend, evaluate_guardrail, check_policy, get_budget_status, list_alerts, get_compliance_status, route_model, get_savings_report, router_explain, evaluate_trust_score, write_memory, registry_publish, registry_review, bridge_mcp_to_a2a, bridge_a2a_to_mcp, bridge_generate_agent_card, bridge_list_mappings, a2a_log, a2a_set_policy, a2a_flow_map, a2a_audit, start_trace, log_event, end_trace, get_trace, get_observability_dashboard, set_baseline, log_decision, decision_cost, log_risk_avoidance, agent_roi, business_impact, detect_waste, register_claim, verify_claim, get_proof, verification_dashboard, policy_create, policy_evaluate, policy_list, policy_violations, compliance_generate, compliance_list, benchmark_compare, benchmark_report, sla_define, sla_status, sla_dashboard, sla_breaches

### P3 — 24 A2A Skills (24/24 passed)

Each skill tested via live A2A Protocol (JSON-RPC `tasks/send` to `agent.thinkneo.ai/a2a`):

check, usage, provider_status, schedule_demo, read_memory, write_memory, check_spend, evaluate_guardrail, check_policy, get_budget_status, list_alerts, get_compliance_status, detect_secrets, detect_injection, compare_models, optimize_prompt, count_tokens, detect_pii, cache_prompt, rotate_key, bridge_mcp_to_a2a, bridge_a2a_to_mcp, bridge_generate_agent_card, bridge_list_mappings

### P3b — A2A Governance E2E (7/7 passed)

| Step | Tool | Result |
|------|------|--------|
| 1. Client sends A2A task | `tasks/send` | completed |
| 2. Set policy between agents | `thinkneo_a2a_set_policy` | OK |
| 3. Bridge MCP→A2A | `thinkneo_bridge_mcp_to_a2a` | OK |
| 4. Log interaction | `thinkneo_a2a_log` (task_sent) | OK |
| 5. Log completion | `thinkneo_a2a_log` (task_completed) | OK |
| 6. Flow map | `thinkneo_a2a_flow_map` | OK |
| 7. Audit trail | `thinkneo_a2a_audit` | OK |

## How to Reproduce

```bash
cd /opt/thinkneo-mcp-server

# MCP tools (59 tools)
PYTHONPATH=. pytest tests/functional/test_every_mcp_tool.py -v --timeout=60

# A2A skills (24 skills)
PYTHONPATH=. pytest tests/functional/test_every_a2a_skill.py -v --timeout=60

# A2A governance E2E (7 steps)
PYTHONPATH=. pytest tests/functional/test_a2a_governance_e2e.py -v --timeout=60
```
