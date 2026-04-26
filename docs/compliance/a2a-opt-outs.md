# A2A Protocol — Intentional Opt-Outs

**Protocol:** A2A v0.3.0 (Google / Linux Foundation)
**Compliance:** 82/82 intentional (80 pass + 2 documented opt-outs)
**Last validated:** 2026-03-21

---

## Summary

ThinkNEO's A2A implementation passes 80 of 82 TCK tests. The 2 remaining are **OPTIONAL** capabilities that we intentionally do not implement because they conflict with our core governance guarantees.

Both opt-outs are architectural decisions, not oversights. They protect the audit trail and compliance posture that enterprise customers rely on.

---

## Opt-Out 1: Batch Task Processing

| Field | Value |
|-------|-------|
| **TCK test** | `optional_capability_batch_tasks` |
| **Spec reference** | A2A v0.3.0, Section 4.2 |
| **Spec status** | OPTIONAL |
| **Our behavior** | Returns `-32600 Invalid Request` for JSON-RPC batch arrays |

### Why we opt out

Every task must individually pass through the full governance pipeline:

```
ACL check → Policy evaluation → Accountability chain → Audit log
```

Batch processing would either:
1. **Skip per-task governance** — creating an audit gap (SOC2 violation)
2. **Require per-item-in-batch governance** — adding complexity and latency without demonstrated customer demand

### Impact on interoperability

- Single-task requests work normally (100% of current consumer usage)
- Agent card does NOT advertise `batch` capability — compliant clients won't attempt batch
- Non-compliant clients sending batch arrays receive a clear error with explanation

### Roadmap

Will implement when:
- A consumer demonstrates batch requirement
- Per-item governance hooks are validated for SOC2 compliance
- Estimated effort: 2-3 engineering hours

---

## Opt-Out 2: Task Priority Routing

| Field | Value |
|-------|-------|
| **TCK test** | `optional_capability_task_priority` |
| **Spec reference** | A2A v0.3.0, Section 3.4 |
| **Spec status** | OPTIONAL |
| **Our behavior** | `priority` field accepted and stored, but does not affect execution order |

### Why we opt out

ThinkNEO processes all tasks in **FIFO order** through the governance pipeline, ensuring:
- **Deterministic execution** — same inputs always produce same ordering
- **Auditable sequence** — SOC2 audit trails expect sequential, time-ordered processing
- **No privilege escalation** — no task can "jump the queue" without audit trail

Priority-based routing would introduce non-deterministic ordering that complicates compliance reporting.

### Impact on interoperability

- The `priority` field IS accepted (no rejection) — graceful degradation
- Stored in task metadata for observability
- Execution remains FIFO regardless of priority value
- Agent card does NOT advertise `priority` capability

### Roadmap

Planned for Enterprise tier with:
- SLA-based priority queues (not arbitrary priority)
- Audited priority overrides (who escalated, when, why)
- Compliance-compatible priority semantics
- Estimated effort: 4-6 engineering hours

---

## Verification

```bash
# Run the official A2A TCK
git clone https://github.com/google/A2A.git && cd A2A/tck
export A2A_AGENT_URL=https://agent.thinkneo.ai/a2a
export A2A_AGENT_CARD_URL=https://mcp.thinkneo.ai/.well-known/agent.json
python3 -m pytest . -v --tb=short
# Result: 80 passed, 2 failed (both in optional_capability category)
```

---

## Compliance Position

Per A2A v0.3.0 specification:
> "Implementations SHOULD support optional capabilities where feasible, but MAY omit them. Omitted capabilities MUST be documented and MUST NOT be advertised in the agent card."

ThinkNEO fully complies with this requirement:
1. Both capabilities are documented (this file + TCK_REPORT.md)
2. Neither is advertised in the agent card
3. Both are handled gracefully (no crashes, clear error messages)

**Enterprise auditors:** This document serves as the official rationale for both opt-outs. For questions, contact hello@thinkneo.ai.
