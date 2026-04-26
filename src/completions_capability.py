"""
MCP Completions Capability — spec 2024-11-05.

Provides autocomplete for prompt arguments via completion/complete.
Supports:
  - workspace: auth-scoped, queries DB for user's workspaces
  - provider: public list of supported AI providers
  - model: provider-aware, filters by provider context hint
  - sample_prompt: free text, returns empty (no completion)
"""

from __future__ import annotations

import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import (
    Completion,
    CompletionArgument,
    CompletionContext,
    PromptReference,
    ResourceTemplateReference,
)

from .auth import get_bearer_token
from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider + Model data
# ---------------------------------------------------------------------------

PROVIDERS = ["anthropic", "openai", "google", "mistral", "nvidia"]

MODELS_BY_PROVIDER: dict[str, list[str]] = {
    "anthropic": [
        "claude-3-5-sonnet", "claude-3-5-haiku",
        "claude-3-opus", "claude-3-haiku",
        "claude-sonnet-4", "claude-opus-4", "claude-opus-4-7",
    ],
    "openai": [
        "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini",
        "o1-preview", "o1-mini", "o3-mini",
    ],
    "google": [
        "gemini-1.5-pro", "gemini-1.5-flash",
        "gemini-2.0-flash", "gemini-2.0-pro",
    ],
    "mistral": [
        "mistral-large", "mistral-medium", "mistral-small",
    ],
    "nvidia": [
        "nemotron-70b", "nemotron-340b", "llama-3.1-nemotron",
    ],
}

ALL_MODELS = sorted({m for models in MODELS_BY_PROVIDER.values() for m in models})

# Prompts that support completions
_PROMPT_COMPLETIONS = {
    "thinkneo_governance_audit": {"workspace"},
    "thinkneo_policy_preflight": {"workspace", "provider", "model", "sample_prompt"},
}


# ---------------------------------------------------------------------------
# Completion logic per argument
# ---------------------------------------------------------------------------

def _complete_workspace(prefix: str) -> Completion:
    """Return workspaces visible to the current user (auth-scoped)."""
    token = get_bearer_token()
    if not token:
        return Completion(values=[])  # Anonymous: empty, not error (privacy)

    key_h = hash_key(token)
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Get distinct workspaces from usage_log for this key
                cur.execute(
                    """
                    SELECT DISTINCT tool_name FROM usage_log
                    WHERE key_hash = %s
                    ORDER BY tool_name
                    LIMIT 100
                    """,
                    (key_h,),
                )
                # We don't have a workspaces table yet — return key prefix as workspace
                # This is a placeholder until proper workspace management is implemented
                values = [key_h[:8] + "-workspace"]
                if prefix:
                    values = [v for v in values if v.startswith(prefix)]
                return Completion(values=values[:100])
    except Exception:
        return Completion(values=[])


def _complete_provider(prefix: str) -> Completion:
    """Return supported AI providers, filtered by prefix."""
    values = [p for p in PROVIDERS if p.startswith(prefix.lower())]
    return Completion(values=values[:100], total=len(values))


def _complete_model(prefix: str, context: Optional[CompletionContext]) -> Completion:
    """Return models, optionally filtered by provider from context."""
    # Check if provider is in context arguments
    provider_hint = None
    if context and context.arguments:
        provider_hint = context.arguments.get("provider", "").lower()

    if provider_hint and provider_hint in MODELS_BY_PROVIDER:
        candidates = MODELS_BY_PROVIDER[provider_hint]
    else:
        candidates = ALL_MODELS

    values = [m for m in candidates if m.startswith(prefix.lower())]
    return Completion(values=values[:100], total=len(values))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_completions(mcp: FastMCP) -> None:
    """Register the completion/complete handler on the low-level server."""

    @mcp._mcp_server.completion()
    async def handle_complete(
        ref: PromptReference | ResourceTemplateReference,
        argument: CompletionArgument,
        context: Optional[CompletionContext],
    ) -> Optional[Completion]:
        # Only handle prompt references
        if not isinstance(ref, PromptReference):
            return Completion(values=[])

        prompt_name = ref.name
        arg_name = argument.name
        prefix = argument.value or ""

        # Check if this prompt supports completions
        if prompt_name not in _PROMPT_COMPLETIONS:
            return Completion(values=[])

        supported_args = _PROMPT_COMPLETIONS[prompt_name]
        if arg_name not in supported_args:
            return Completion(values=[])

        # Dispatch to argument-specific completion
        if arg_name == "workspace":
            return _complete_workspace(prefix)
        elif arg_name == "provider":
            return _complete_provider(prefix)
        elif arg_name == "model":
            return _complete_model(prefix, context)
        else:
            # sample_prompt and others: no completion available
            return Completion(values=[])
