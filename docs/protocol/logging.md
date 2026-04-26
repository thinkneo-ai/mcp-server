# Logging Capability

> **MCP Spec:** 2024-11-05
> **Implementation:** `src/logging_capability.py`
> **Tests:** `tests/unit/test_logging_capability.py` (8 tests)

## Overview

ThinkNEO supports the MCP logging capability, allowing clients to control the server-side log level and receive filtered log notifications.

## logging/setLevel

Set the minimum log level for the current session.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "logging/setLevel",
  "params": {
    "level": "debug"
  }
}
```

### Supported Levels

| MCP Level | Python Mapping | Numeric |
|-----------|---------------|---------|
| debug | DEBUG | 10 |
| info | INFO | 20 |
| notice | INFO | 20 |
| warning | WARNING | 30 |
| error | ERROR | 40 |
| critical | CRITICAL | 50 |
| alert | CRITICAL | 50 |
| emergency | CRITICAL | 50 |

### Behavior

- Default level per session: `info`
- Level persists for the duration of the session (stateless HTTP: each request is independent, so level resets to `info` per request)
- Invalid level: rejected with JSON-RPC error `-32602`
- Every level change is logged to the audit trail (`usage_log` table)

## Audit Trail

Level changes are recorded in `usage_log` with:
- `tool_name`: `logging/setLevel`
- `key_hash`: the caller's API key hash (or "anonymous")
- `called_at`: timestamp of the change
