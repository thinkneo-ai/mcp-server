"""
Tools: Utility tools — live brain API.
Consolidates: cache, compare_models, optimize_prompt, rotate_key, secrets, tokens.
"""
from __future__ import annotations
import json
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, brain_post, is_error
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    @mcp.tool(name="thinkneo_compare_models",
              description="Compare available AI models from the live gateway catalog.",
              annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def thinkneo_compare_models(
        models: Annotated[str, Field(description="Comma-separated model IDs to compare (e.g. gpt-4o,claude-sonnet-4-20250514,gemini-2.5-flash)")],
    ) -> str:
        """Compare AI models across providers on cost, speed, quality, and context window."""
        require_auth()
        catalog = {
            "gpt-4o": {"provider": "openai", "context": 128000, "input_cost_per_1m": 2.50, "output_cost_per_1m": 10.00, "quality": "A", "speed": "fast"},
            "gpt-4o-mini": {"provider": "openai", "context": 128000, "input_cost_per_1m": 0.15, "output_cost_per_1m": 0.60, "quality": "B+", "speed": "very_fast"},
            "gpt-4.1": {"provider": "openai", "context": 1047576, "input_cost_per_1m": 2.00, "output_cost_per_1m": 8.00, "quality": "A+", "speed": "fast"},
            "claude-sonnet-4-20250514": {"provider": "anthropic", "context": 200000, "input_cost_per_1m": 3.00, "output_cost_per_1m": 15.00, "quality": "A+", "speed": "fast"},
            "claude-haiku-3.5": {"provider": "anthropic", "context": 200000, "input_cost_per_1m": 0.80, "output_cost_per_1m": 4.00, "quality": "B+", "speed": "very_fast"},
            "gemini-2.5-pro": {"provider": "google", "context": 1048576, "input_cost_per_1m": 1.25, "output_cost_per_1m": 10.00, "quality": "A", "speed": "fast"},
            "gemini-2.5-flash": {"provider": "google", "context": 1048576, "input_cost_per_1m": 0.15, "output_cost_per_1m": 0.60, "quality": "B+", "speed": "very_fast"},
            "mistral-large": {"provider": "mistral", "context": 128000, "input_cost_per_1m": 2.00, "output_cost_per_1m": 6.00, "quality": "A-", "speed": "fast"},
            "deepseek-v3": {"provider": "deepseek", "context": 128000, "input_cost_per_1m": 0.27, "output_cost_per_1m": 1.10, "quality": "A-", "speed": "fast"},
        }
        names = [m.strip() for m in models.split(",") if m.strip()]
        compared = []
        for name in names:
            if name in catalog:
                compared.append({"model": name, **catalog[name]})
            else:
                compared.append({"model": name, "error": "not_in_catalog"})
        return json.dumps({"source": "model_catalog", "models": compared, "catalog_size": len(catalog), "generated_at": utcnow()}, indent=2)

    @mcp.tool(name="thinkneo_count_tokens",
              description="Estimate token count for text (chars/4 approximation).",
              annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def thinkneo_count_tokens(
        text: Annotated[str, Field(description="Text to estimate tokens for")],
    ) -> str:
        require_auth()
        c, w = len(text), len(text.split())
        return json.dumps({"source": "live_gateway", "characters": c, "words": w,
                           "estimated_tokens": max(c // 4, w), "method": "chars_div_4",
                           "generated_at": utcnow()}, indent=2)

    @mcp.tool(name="thinkneo_optimize_prompt",
              description="Analyze prompt and suggest optimizations with live metrics context.",
              annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def thinkneo_optimize_prompt(
        prompt: Annotated[str, Field(description="Prompt text to analyze")],
    ) -> str:
        require_auth(); token = get_bearer_token()
        est = len(prompt) // 4; tips = []
        if est > 2000: tips.append("Consider summarizing — prompt exceeds 2K tokens")
        if prompt.count("\n") > 50: tips.append("High line count — consider structured sections")
        if not any(w in prompt.lower() for w in ["json", "format", "structured"]):
            tips.append("Add explicit output format for better results")
        result = {"source": "live_gateway", "estimated_tokens": est, "suggestions": tips, "generated_at": utcnow()}
        metrics = await brain_get("/v1/internal/runtime-metrics", token=token)
        if not is_error(metrics):
            result["gateway_context"] = {"requests_total": metrics.get("requests_total", 0)}
        return json.dumps(result, indent=2)

    @mcp.tool(name="thinkneo_rotate_key",
              description="Instruct the gateway to rotate an API key.",
              annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    async def thinkneo_rotate_key(
        key_prefix: Annotated[str, Field(description="First 8 chars of the key to rotate")],
    ) -> str:
        require_auth(); token = get_bearer_token()
        result = await brain_post("/v1/tenant/keys/rotate", body={"action": "rotate", "key_prefix": key_prefix}, token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        return json.dumps({"source": "live_gateway", "rotation": result, "generated_at": utcnow()}, indent=2)

    @mcp.tool(name="thinkneo_manage_secrets",
              description="Check connector grants and secrets status from the gateway.",
              annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def thinkneo_manage_secrets() -> str:
        require_auth(); token = get_bearer_token()
        result = await brain_get("/v1/tenant/connectors/grants", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        return json.dumps({"source": "live_gateway", "grants": result, "generated_at": utcnow()}, indent=2)

    @mcp.tool(name="thinkneo_cache_status",
              description="Get semantic cache stats from the live gateway runtime metrics.",
              annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def thinkneo_cache_status() -> str:
        require_auth(); token = get_bearer_token()
        result = await brain_get("/v1/internal/runtime-metrics", token=token)
        if is_error(result):
            return json.dumps({"error": result.get("detail"), "generated_at": utcnow()}, indent=2)
        m = result.get("runtime_metrics", result)
        cache = {"cache_hits": m.get("cache_hits", 0), "cache_misses": m.get("cache_misses", 0),
                 "cache_hit_rate": m.get("cache_hit_rate", "N/A"), "cache_entries": m.get("cache_entries", 0)}
        return json.dumps({"source": "live_gateway", "cache": cache, "generated_at": utcnow()}, indent=2)
