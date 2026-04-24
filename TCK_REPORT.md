# A2A Protocol TCK Compliance Report

> **ThinkNEO MCP+A2A Gateway** -- Protocol v0.3.0
> Last run: 2026-03-21
> Result: **80/82 passing (97.6%)**

---

## About the TCK

The Technology Compatibility Kit (TCK) is the official test suite published by Google as part of the [A2A Protocol](https://github.com/google/A2A) project, now maintained under the Linux Foundation. It validates that an A2A implementation correctly handles agent discovery, task lifecycle, messaging, streaming, and error conditions as defined in the specification.

TCK compliance is the industry-standard way to verify interoperability between A2A agents.

---

## Results by Category

| Category | Passing | Failing | Total | Notes |
|----------|---------|---------|-------|-------|
| Agent Discovery | 8 | 0 | 8 | `/.well-known/agent.json` served correctly |
| Task Lifecycle | 14 | 0 | 14 | send, get, cancel, list |
| Message Format | 10 | 0 | 10 | Text parts, structured data |
| Streaming | 8 | 0 | 8 | SSE event stream |
| Authentication | 6 | 0 | 6 | Bearer token validation |
| Error Handling | 12 | 0 | 12 | JSON-RPC error codes |
| Push Notifications | 6 | 0 | 6 | Webhook callbacks |
| Multi-turn | 8 | 0 | 8 | Conversation context |
| Optional Capabilities | 8 | 2 | 10 | See below |
| **Total** | **80** | **2** | **82** | **97.6%** |

---

## Failing Tests

### 1. `optional_capability_batch_tasks`

- **What it tests**: JSON-RPC batch arrays (multiple tasks in one HTTP request)
- **Spec status**: **Optional** — A2A v0.3.0 Section 4.2 "Batch Processing" is marked `OPTIONAL`
- **Our behavior**: Returns `-32600 Invalid Request` for array payloads. Agent card declares `capabilities.streaming: false` — batch is not advertised.
- **Why not implemented**: Each task passes through the governance pipeline (ACL check → policy evaluation → accountability chain). Batch processing would need per-item governance hooks, adding complexity without demand from current consumers.
- **Can we fix it?**: Yes — add array detection at line 266 of `server.py`, loop over items, process each through existing pipeline, return array of results. Estimated effort: 2-3 hours.
- **Decision**: Not implemented by design. Governance integrity > batch throughput. Will implement when a consumer requires it.

### 2. `optional_capability_task_priority`

- **What it tests**: That the `priority` field on task submission affects execution order
- **Spec status**: **Optional** — A2A v0.3.0 Section 3.4 "Task Priority" is marked `OPTIONAL`
- **Our behavior**: The `priority` field is **accepted and stored** in the task object (no rejection). However, execution order is FIFO — priority does not affect routing.
- **Why not implemented**: All tasks go through the same governance pipeline. Priority-based routing requires a queue system (Redis sorted sets or similar) that adds operational complexity for a feature no consumer has requested.
- **Can we fix it?**: Yes — add priority sorting to task dispatch. Estimated effort: 4-6 hours.
- **Decision**: Not implemented by design. The field is accepted gracefully (no error), just not acted upon. Will implement for Enterprise tier with SLA-based queues.

---

## How to Reproduce

Run the official A2A TCK against the live endpoint:

```bash
# Clone the official A2A TCK
git clone https://github.com/google/A2A.git
cd A2A/tck

# Point to ThinkNEO's A2A agent
export A2A_AGENT_URL=https://agent.thinkneo.ai/a2a
export A2A_AGENT_CARD_URL=https://mcp.thinkneo.ai/.well-known/agent.json

# Run the test suite
python3 -m pytest . -v --tb=short
```

Expected output: 80 passed, 2 failed (both in `optional_capability` category).

---

## History

| Date | Score | Notes |
|------|-------|-------|
| 2026-03-21 | 80/82 (97.6%) | Initial TCK run after A2A v0.3.0 implementation |

---

## Related

- [A2A Protocol Specification](https://github.com/google/A2A)
- [ThinkNEO Agent Card](https://mcp.thinkneo.ai/.well-known/agent.json)
- [ThinkNEO MCP+A2A Gateway](https://github.com/thinkneo-ai/mcp-server)
