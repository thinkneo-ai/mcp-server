# Completions Capability

> **MCP Spec:** 2024-11-05
> **Implementation:** `src/completions_capability.py`
> **Tests:** `tests/unit/test_completions_capability.py` (12 tests)

## Overview

ThinkNEO supports the MCP completions capability, providing autocomplete for prompt arguments via `completion/complete`.

## completion/complete

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "completion/complete",
  "params": {
    "ref": { "type": "ref/prompt", "name": "thinkneo_policy_preflight" },
    "argument": { "name": "provider", "value": "ant" },
    "context": { "arguments": {} }
  }
}
```

Response:
```json
{
  "completion": {
    "values": ["anthropic"],
    "total": 1
  }
}
```

## Prompts with Completions

### thinkneo_governance_audit

| Argument | Auth Required | Source |
|----------|--------------|--------|
| workspace | Yes | User's workspaces from DB |

### thinkneo_policy_preflight

| Argument | Auth Required | Source |
|----------|--------------|--------|
| workspace | Yes | User's workspaces from DB |
| provider | No | Static list: anthropic, openai, google, mistral, nvidia |
| model | No | Provider-aware: filtered by `context.arguments.provider` |
| sample_prompt | N/A | Free text — no completion |

## Provider-Aware Model Completion

When the client includes `provider` in `context.arguments`, model completion returns only that provider's models:

| Provider | Models |
|----------|--------|
| anthropic | claude-3-5-sonnet, claude-3-5-haiku, claude-3-opus, claude-3-haiku, claude-sonnet-4, claude-opus-4, claude-opus-4-7 |
| openai | gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, o1-preview, o1-mini, o3-mini |
| google | gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash, gemini-2.0-pro |
| mistral | mistral-large, mistral-medium, mistral-small |
| nvidia | nemotron-70b, nemotron-340b, llama-3.1-nemotron |

Without provider context, all models from all providers are returned.

## Auth Handling

- **workspace**: Requires authentication. Anonymous callers receive empty `values: []` (privacy-by-default — no error revealed).
- **provider/model**: Public information. Works for all callers including anonymous.
- **Unknown prompt/argument**: Returns empty `values: []`, not an error.
