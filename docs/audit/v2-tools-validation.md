# v2.0.0 Orphan Tools — Compatibility Validation

**Date:** 2026-04-26
**Context:** 8 files with 10 `@mcp.tool` decorators from v2.0.0 (Apr 17) were never imported by `__init__.py`. Before registration, each is validated against the current v3.12.0 codebase.

## Validation Criteria

| Check | Method |
|-------|--------|
| Imports valid | `python3 -c "import src.tools.{module}"` — all 8 pass |
| `register()` exists | `grep "^def register"` — all 8 have it |
| Internal deps exist | `src/tools/_common.py` (utcnow), `src/plans.py` (require_plan), `src/database.py` (_get_conn, hash_key), `src/auth.py` (get_bearer_token) — all present |
| Auth pattern correct | Pro tools use `require_plan("pro")`, public tools use no auth gate |
| Middleware applied | `_wrap_tools_with_free_tier()` auto-wraps ALL tools post-registration (OTEL + rate limit + usage footer) |
| Redaction covered | Log redaction operates at logging framework level, not per-tool |
| Annotations present | All have `ToolAnnotations(readOnlyHint, destructiveHint, ...)` from SEC-02 (Apr 25) |

## Per-Module Validation

### 1. cache.py (3 tools) — REQUIRES DB

| Item | Status |
|------|--------|
| Auth | `require_plan("pro")` on all 3 tools |
| DB access | `_get_conn()` — same pattern as 30+ registered tools |
| Schema dep | Requires `cache_entries` table (exists in migrations) |
| Security | No raw user input in SQL (parameterized) |
| Risk | LOW — enterprise-only, behind paywall |

### 2. compare_models.py (1 tool) — PURE LOGIC

| Item | Status |
|------|--------|
| Auth | None (public tool) |
| DB access | None |
| Dependencies | Only `_common.utcnow()` |
| Security | Static catalog, no user-influenced computation |
| Risk | NONE |

### 3. injection.py (1 tool) — PURE LOGIC

| Item | Status |
|------|--------|
| Auth | None (public tool) |
| DB access | None |
| Dependencies | `re`, `base64`, `unicodedata`, `_common.utcnow()` |
| Security | Input capped at 50,000 chars. Read-only regex matching. |
| Risk | NONE — this tool IMPROVES security posture |

### 4. optimize_prompt.py (1 tool) — PURE LOGIC

| Item | Status |
|------|--------|
| Auth | None (public tool) |
| DB access | None |
| Dependencies | `re`, `_common.utcnow()` |
| Security | Input capped at 20,000 chars. Deterministic string ops. |
| Risk | NONE |

### 5. pii_intl.py (1 tool) — PURE LOGIC

| Item | Status |
|------|--------|
| Auth | None (public tool) |
| DB access | None |
| Dependencies | `re`, `_common.utcnow()` |
| Security | Input capped at 100,000 chars. Luhn validation for credit cards. |
| Risk | NONE — this tool IMPROVES security posture |

### 6. rotate_key.py (1 tool) — REQUIRES DB + AUTH

| Item | Status |
|------|--------|
| Auth | `require_plan("pro")` + `get_bearer_token()` |
| DB access | `_get_conn()` + `hash_key()` — reads/writes `api_keys` and `revoked_keys` |
| Schema dep | Tables `api_keys`, `revoked_keys` (both exist in migrations) |
| Security | ⚠️ **MOST SENSITIVE** — generates new API keys, revokes old ones |
| Mitigation | `require_plan("pro")` gates access; only the key's own holder can rotate |
| Risk | LOW — properly gated, parameterized SQL, logged |

### 7. secrets.py (1 tool) — PURE LOGIC

| Item | Status |
|------|--------|
| Auth | None (public tool) |
| DB access | None |
| Dependencies | `re`, `_common.utcnow()` |
| Security | Input capped at 100,000 chars. Returns **masked** matches only. |
| Risk | NONE — this tool IMPROVES security posture |
| Note | Uses `MCP_REDIS_URL` env reference in pattern list (detecting Redis URIs in user text) |

### 8. tokens.py (1 tool) — PURE LOGIC

| Item | Status |
|------|--------|
| Auth | None (public tool) |
| DB access | None |
| Dependencies | `re`, `_common.utcnow()` |
| Security | Pure arithmetic on static pricing table. |
| Risk | NONE |

## Middleware Coverage (applies automatically after registration)

All tools pass through `_wrap_tools_with_free_tier()` which provides:
1. **Free-tier rate limiting** — anonymous: 30/hour IP rate limit via Redis
2. **OTEL instrumentation** — spans + counters if `OTEL_ENABLED=true`
3. **Usage footer** — `_usage` block appended to JSON responses

No per-tool changes needed. This is the same middleware protecting existing 62 tools.

## Summary

| Category | Files | Tools | Risk |
|----------|-------|-------|------|
| Pure logic (public) | 6 | 7 | NONE |
| DB + auth (enterprise) | 2 | 3 | LOW (properly gated) |
| **Total** | **8** | **10** | **SAFE TO REGISTER** |

## Decision

**PROCEED WITH REGISTRATION.** No code changes needed in the tool modules themselves — they are already compatible with the current codebase architecture (FastMCP, ToolAnnotations, _common.utcnow, require_plan, _get_conn).
