# Registry Investigation — GAP 3

**Date:** 2026-04-26
**Investigator:** Claude Opus 4.6
**Conclusion:** Omission bug, not intentional exclusion

## Problem Statement

72 `@mcp.tool` decorators exist in `src/tools/`, but only 62 tools are registered in production (`tools/list`). Difference: 10 decorators across 8 files.

## Root Cause

**`src/tools/__init__.py` does not import 8 tool modules.** These modules:
1. Have valid `register(mcp)` functions
2. Import cleanly (no errors)
3. Have no conditional logic or feature flags
4. Were created in commit `9b17027` (v2.0.0, Apr 17)
5. Were never added to `__init__.py` when it was restructured during the 10-feature roadmap (Apr 24-25)

This is a **registration omission**, not a deliberate exclusion.

## Evidence

### Check 1: No try/except silencing registration failures
```
grep "try\|except" src/tools/__init__.py
→ Only in _wrap_tools_with_free_tier() (unrelated to registration)
```

### Check 2: No conditional imports
```
grep "if.*env\|if.*os.getenv\|if.*settings" src/tools/__init__.py
→ 0 results
```

### Check 3: All 8 orphan files import cleanly
```python
for mod in [cache, compare_models, injection, optimize_prompt,
            pii_intl, rotate_key, secrets, tokens]:
    import src.tools.{mod}  # All OK, no exceptions
```

### Check 4: All have register() function
| File | register() at line |
|------|--------------------|
| cache.py | 39 |
| compare_models.py | 160 |
| injection.py | 164 |
| optimize_prompt.py | 165 |
| pii_intl.py | 147 |
| rotate_key.py | 34 |
| secrets.py | 137 |
| tokens.py | 76 |

### Check 5: Production confirms 62 tools
```
curl mcp.thinkneo.ai/mcp -d '{"method":"tools/list"}' | grep thinkneo_ | wc -l
→ 62
```

## Orphan Files (8 files, 10 decorators)

| File | Tools | Decorator count | Purpose |
|------|-------|-----------------|---------|
| `cache.py` | cache_lookup, cache_store, cache_stats | 3 | Response caching |
| `compare_models.py` | compare_models | 1 | Model price/capability comparison |
| `injection.py` | detect_injection | 1 | Advanced prompt injection detection |
| `optimize_prompt.py` | optimize_prompt | 1 | Token-reducing prompt optimizer |
| `pii_intl.py` | check_pii_international | 1 | International PII detection (LGPD/GDPR/HIPAA) |
| `rotate_key.py` | rotate_key | 1 | API key rotation |
| `secrets.py` | scan_secrets | 1 | Secret/credential scanner |
| `tokens.py` | estimate_tokens | 1 | Token count & cost estimator |

## Timeline

1. **Apr 17** — v2.0.0 commit creates all 8 files with `@mcp.tool` + `register()`
2. **Apr 24** — `__init__.py` restructured for roadmap features (observability, value tools, A2A, etc.)
3. **Apr 25** — SEC-02 audit touches all 72 files (adds annotations) but doesn't fix registration
4. **Apr 26** — Investigation reveals the omission

## Recommendation

**Register all 8 modules.** They are production-ready:
- All have docstrings, proper auth checks, annotations
- All follow the same pattern as registered tools
- Several are high-value SEO tools (tokens, compare_models, secrets)
- `cache.py` is critical for the FinOps caching feature

After registration, tool count will be: **62 + 10 = 72 (decorator count == registered count)**

## Verification Method

After fix, confirm:
```bash
# Local
python3 -c "from src.tools import register_all; from mcp.server.fastmcp import FastMCP; m=FastMCP('test'); register_all(m); print(len(m._tool_manager._tools))"
# → Should print 72

# Production
curl mcp.thinkneo.ai/mcp -d '{"method":"tools/list"}' | grep -c thinkneo_
# → Should print 72
```
