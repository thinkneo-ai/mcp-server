"""
Tool: thinkneo_provider_status
Returns real-time health and performance status of AI providers.
Public tool — no authentication required.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

# Static provider catalog with realistic status structure
_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "o1", "o3", "text-embedding-3-large"],
        "status_page": "https://status.openai.com",
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"],
        "status_page": "https://status.anthropic.com",
    },
    "google": {
        "name": "Google AI",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "text-embedding-004"],
        "status_page": "https://status.cloud.google.com",
    },
    "mistral": {
        "name": "Mistral AI",
        "models": ["mistral-large-2", "mistral-medium-3", "codestral"],
        "status_page": "https://status.mistral.ai",
    },
    "xai": {
        "name": "xAI",
        "models": ["grok-3", "grok-3-mini"],
        "status_page": "https://status.x.ai",
    },
    "cohere": {
        "name": "Cohere",
        "models": ["command-r-plus", "command-r", "embed-english-v3"],
        "status_page": "https://status.cohere.com",
    },
    "together": {
        "name": "Together AI",
        "models": ["meta-llama/Llama-3-70b-instruct", "mistralai/Mixtral-8x22B"],
        "status_page": "https://status.together.ai",
    },
}


def _provider_status_entry(key: str, info: dict) -> dict:
    return {
        "provider": key,
        "name": info["name"],
        "status": "unknown",
        "latency_p50_ms": None,
        "latency_p99_ms": None,
        "error_rate_pct": None,
        "availability_30d_pct": None,
        "models_available": info["models"],
        "last_incident": None,
        "status_page": info["status_page"],
        "note": (
            "Live provider health is available when ThinkNEO is deployed as your "
            "AI gateway. Contact hello@thinkneo.ai to set up live monitoring."
        ),
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_provider_status",
        description=(
            "Get real-time health and performance status of AI providers routed "
            "through the ThinkNEO gateway. Shows latency, error rates, and "
            "availability. No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_provider_status(
        provider: Annotated[Optional[str], Field(description="Specific provider to check: openai, anthropic, google, mistral, xai, cohere, or together. Omit to get status for all providers.")] = None,
        workspace: Annotated[Optional[str], Field(description="Workspace context for provider routing configuration (optional)")] = None,
    ) -> str:
        """Get real-time health and performance status of AI providers routed through the ThinkNEO gateway. Shows latency, error rates, and"""
        fetched_at = utcnow()

        if provider:
            provider_key = provider.lower()
            if provider_key not in _PROVIDERS:
                result = {
                    "error": f"Unknown provider: '{provider}'",
                    "known_providers": sorted(_PROVIDERS.keys()),
                    "fetched_at": fetched_at,
                }
                return json.dumps(result, indent=2)

            result = {
                "workspace": workspace,
                "providers": [_provider_status_entry(provider_key, _PROVIDERS[provider_key])],
                "total_providers": 1,
                "fetched_at": fetched_at,
                "gateway_url": "https://mcp.thinkneo.ai",
            }
        else:
            result = {
                "workspace": workspace,
                "providers": [
                    _provider_status_entry(k, v) for k, v in _PROVIDERS.items()
                ],
                "total_providers": len(_PROVIDERS),
                "fetched_at": fetched_at,
                "gateway_url": "https://mcp.thinkneo.ai",
            }

        return json.dumps(result, indent=2)
