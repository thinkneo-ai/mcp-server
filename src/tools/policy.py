"""
Tool: thinkneo_check_policy
Checks if a model, provider, or action is allowed by workspace governance policies.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ._common import demo_note, utcnow, validate_workspace

# Demo blocklist — replace with real policy engine calls
_BLOCKED_MODELS: set[str] = {"gpt-4-raw", "unrestricted-model", "llama-uncensored"}
_BLOCKED_PROVIDERS: set[str] = set()  # All providers allowed in demo


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_check_policy",
        description=(
            "Check if a specific model, provider, or action is allowed by the "
            "governance policies configured for a workspace. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_check_policy(
        workspace: Annotated[str, Field(description="Workspace name or ID whose governance policies to check against")],
        model: Annotated[Optional[str], Field(description="AI model name to check (e.g., gpt-4o, claude-sonnet-4-6, gemini-2.0-flash)")] = None,
        provider: Annotated[Optional[str], Field(description="AI provider to check (e.g., openai, anthropic, google, mistral)")] = None,
        action: Annotated[Optional[str], Field(description="Specific action to check (e.g., create-completion, use-tool, fine-tune)")] = None,
    ) -> str:
        """Check if a specific model, provider, or action is allowed by the governance policies configured for a workspace."""
        require_auth()
        workspace = validate_workspace(workspace)

        checks: list[dict] = []
        overall_allowed = True

        if model:
            model_blocked = model.lower() in _BLOCKED_MODELS
            checks.append(
                {
                    "type": "model",
                    "value": model,
                    "allowed": not model_blocked,
                    "reason": (
                        f"Model '{model}' is on the workspace blocklist."
                        if model_blocked
                        else f"Model '{model}' is permitted by workspace policy."
                    ),
                }
            )
            if model_blocked:
                overall_allowed = False

        if provider:
            provider_blocked = provider.lower() in _BLOCKED_PROVIDERS
            checks.append(
                {
                    "type": "provider",
                    "value": provider,
                    "allowed": not provider_blocked,
                    "reason": (
                        f"Provider '{provider}' is not approved for this workspace."
                        if provider_blocked
                        else f"Provider '{provider}' is an approved provider."
                    ),
                }
            )
            if provider_blocked:
                overall_allowed = False

        if action:
            checks.append(
                {
                    "type": "action",
                    "value": action,
                    "allowed": True,
                    "reason": f"Action '{action}' is permitted by default policy.",
                }
            )

        if not checks:
            checks.append(
                {
                    "type": "workspace",
                    "value": workspace,
                    "allowed": True,
                    "reason": "Workspace exists and is active.",
                }
            )

        result = {
            "workspace": workspace,
            "overall_allowed": overall_allowed,
            "checks": checks,
            "policy_version": "2026-01-01",
            "evaluated_at": utcnow(),
            "policy_url": f"https://thinkneo.ai/workspaces/{workspace}/policies",
            "_demo": demo_note(workspace),
        }

        return json.dumps(result, indent=2)
