"""
Tool: thinkneo_compare_models
Static reference data for price/capability comparison across 25+ models from
8 major providers. Updated: April 2026.
Public tool — no authentication required.

This is a SEO magnet and dev utility. Every developer chooses a model based on
cost × capability × latency tradeoffs. ThinkNEO becomes the source of truth.
"""

from __future__ import annotations

import json
from typing import Annotated, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

# Price/capability catalog (USD per 1M tokens, context windows in tokens)
# Ordered by provider then capability tier.
_CATALOG = [
    # ── OpenAI ──────────────────────────────────────────────────────
    {"provider": "openai", "model": "gpt-5", "input_usd_per_m": 10.0, "output_usd_per_m": 30.0,
     "context": 400_000, "tier": "frontier", "modalities": ["text", "vision"],
     "strengths": ["reasoning", "coding", "long context"], "knowledge_cutoff": "2026-01"},
    {"provider": "openai", "model": "gpt-5-mini", "input_usd_per_m": 0.25, "output_usd_per_m": 1.0,
     "context": 400_000, "tier": "efficient", "modalities": ["text", "vision"],
     "strengths": ["fast", "cheap", "agentic"], "knowledge_cutoff": "2026-01"},
    {"provider": "openai", "model": "gpt-5-nano", "input_usd_per_m": 0.05, "output_usd_per_m": 0.20,
     "context": 128_000, "tier": "tiny", "modalities": ["text"],
     "strengths": ["ultra-fast", "classification", "routing"], "knowledge_cutoff": "2025-10"},
    {"provider": "openai", "model": "o4-mini", "input_usd_per_m": 1.1, "output_usd_per_m": 4.4,
     "context": 200_000, "tier": "reasoning", "modalities": ["text", "vision"],
     "strengths": ["math", "complex reasoning"], "knowledge_cutoff": "2025-06"},
    {"provider": "openai", "model": "gpt-4o", "input_usd_per_m": 2.5, "output_usd_per_m": 10.0,
     "context": 128_000, "tier": "generalist", "modalities": ["text", "vision", "audio"],
     "strengths": ["multimodal", "balanced"], "knowledge_cutoff": "2024-10"},
    # ── Anthropic ───────────────────────────────────────────────────
    {"provider": "anthropic", "model": "claude-opus-4-6", "input_usd_per_m": 15.0, "output_usd_per_m": 75.0,
     "context": 1_000_000, "tier": "frontier", "modalities": ["text", "vision"],
     "strengths": ["writing", "reasoning", "1M context", "coding"], "knowledge_cutoff": "2025-05"},
    {"provider": "anthropic", "model": "claude-sonnet-4-6", "input_usd_per_m": 3.0, "output_usd_per_m": 15.0,
     "context": 1_000_000, "tier": "balanced", "modalities": ["text", "vision"],
     "strengths": ["coding", "1M context", "agentic workflows"], "knowledge_cutoff": "2025-05"},
    {"provider": "anthropic", "model": "claude-haiku-4-5", "input_usd_per_m": 0.8, "output_usd_per_m": 4.0,
     "context": 200_000, "tier": "efficient", "modalities": ["text", "vision"],
     "strengths": ["fast", "cheap", "summarization"], "knowledge_cutoff": "2025-03"},
    # ── Google ──────────────────────────────────────────────────────
    {"provider": "google", "model": "gemini-2.5-pro", "input_usd_per_m": 2.5, "output_usd_per_m": 15.0,
     "context": 2_000_000, "tier": "frontier", "modalities": ["text", "vision", "audio", "video"],
     "strengths": ["2M context", "multimodal", "reasoning"], "knowledge_cutoff": "2025-04"},
    {"provider": "google", "model": "gemini-2.5-flash", "input_usd_per_m": 0.30, "output_usd_per_m": 2.5,
     "context": 1_000_000, "tier": "balanced", "modalities": ["text", "vision", "audio", "video"],
     "strengths": ["fast multimodal", "long context"], "knowledge_cutoff": "2025-04"},
    {"provider": "google", "model": "gemini-2.5-flash-lite", "input_usd_per_m": 0.10, "output_usd_per_m": 0.40,
     "context": 1_000_000, "tier": "efficient", "modalities": ["text", "vision"],
     "strengths": ["ultra cheap", "high throughput"], "knowledge_cutoff": "2024-10"},
    # ── Meta (Llama) ────────────────────────────────────────────────
    {"provider": "meta", "model": "llama-4-scout", "input_usd_per_m": 0.12, "output_usd_per_m": 0.35,
     "context": 10_000_000, "tier": "efficient", "modalities": ["text", "vision"],
     "strengths": ["10M context", "open weights", "cheap"], "knowledge_cutoff": "2025-01"},
    {"provider": "meta", "model": "llama-4-maverick", "input_usd_per_m": 0.20, "output_usd_per_m": 0.70,
     "context": 1_000_000, "tier": "balanced", "modalities": ["text", "vision"],
     "strengths": ["MoE", "open weights", "code"], "knowledge_cutoff": "2025-01"},
    {"provider": "meta", "model": "llama-4-behemoth", "input_usd_per_m": 2.5, "output_usd_per_m": 7.5,
     "context": 1_000_000, "tier": "frontier", "modalities": ["text", "vision"],
     "strengths": ["frontier open weights", "reasoning"], "knowledge_cutoff": "2025-02"},
    # ── Mistral ─────────────────────────────────────────────────────
    {"provider": "mistral", "model": "mistral-large-2-latest", "input_usd_per_m": 2.0, "output_usd_per_m": 6.0,
     "context": 128_000, "tier": "balanced", "modalities": ["text"],
     "strengths": ["multilingual", "function calling", "EU residency"], "knowledge_cutoff": "2025-02"},
    {"provider": "mistral", "model": "mistral-medium-3", "input_usd_per_m": 0.40, "output_usd_per_m": 2.0,
     "context": 128_000, "tier": "efficient", "modalities": ["text", "vision"],
     "strengths": ["EU-hosted", "fast"], "knowledge_cutoff": "2025-01"},
    {"provider": "mistral", "model": "pixtral-large", "input_usd_per_m": 2.0, "output_usd_per_m": 6.0,
     "context": 128_000, "tier": "balanced", "modalities": ["text", "vision"],
     "strengths": ["vision specialist", "document understanding"], "knowledge_cutoff": "2025-01"},
    # ── xAI ─────────────────────────────────────────────────────────
    {"provider": "xai", "model": "grok-4", "input_usd_per_m": 3.0, "output_usd_per_m": 15.0,
     "context": 256_000, "tier": "frontier", "modalities": ["text", "vision"],
     "strengths": ["real-time web", "reasoning"], "knowledge_cutoff": "live"},
    {"provider": "xai", "model": "grok-4-fast", "input_usd_per_m": 0.20, "output_usd_per_m": 0.50,
     "context": 128_000, "tier": "efficient", "modalities": ["text"],
     "strengths": ["real-time", "cheap"], "knowledge_cutoff": "live"},
    # ── DeepSeek ────────────────────────────────────────────────────
    {"provider": "deepseek", "model": "deepseek-v3.5", "input_usd_per_m": 0.27, "output_usd_per_m": 1.10,
     "context": 128_000, "tier": "balanced", "modalities": ["text"],
     "strengths": ["coding", "cheap", "open weights"], "knowledge_cutoff": "2025-03"},
    {"provider": "deepseek", "model": "deepseek-r1", "input_usd_per_m": 0.55, "output_usd_per_m": 2.19,
     "context": 128_000, "tier": "reasoning", "modalities": ["text"],
     "strengths": ["reasoning", "open weights", "cheap"], "knowledge_cutoff": "2025-02"},
    # ── Cohere ──────────────────────────────────────────────────────
    {"provider": "cohere", "model": "command-a-03-2026", "input_usd_per_m": 2.5, "output_usd_per_m": 10.0,
     "context": 256_000, "tier": "balanced", "modalities": ["text"],
     "strengths": ["multilingual", "RAG", "tool use"], "knowledge_cutoff": "2025-03"},
    {"provider": "cohere", "model": "command-r-plus-08-2025", "input_usd_per_m": 2.5, "output_usd_per_m": 10.0,
     "context": 128_000, "tier": "balanced", "modalities": ["text"],
     "strengths": ["RAG", "citations"], "knowledge_cutoff": "2024-08"},
    # ── NVIDIA (Nemotron — free on ThinkNEO) ───────────────────────
    {"provider": "nvidia", "model": "nemotron-nano-12b-v2", "input_usd_per_m": 0.04, "output_usd_per_m": 0.10,
     "context": 128_000, "tier": "efficient", "modalities": ["text"],
     "strengths": ["self-hosted", "free on ThinkNEO", "reasoning"], "knowledge_cutoff": "2025-04"},
    {"provider": "nvidia", "model": "nemotron-ultra-253b", "input_usd_per_m": 1.50, "output_usd_per_m": 4.50,
     "context": 128_000, "tier": "frontier", "modalities": ["text"],
     "strengths": ["open weights", "agentic"], "knowledge_cutoff": "2025-04"},
]


def _filter_catalog(
    use_case: Optional[str],
    max_input_price: Optional[float],
    min_context: Optional[int],
    providers: Optional[List[str]],
    modalities: Optional[List[str]],
) -> List[dict]:
    results = []
    for m in _CATALOG:
        if max_input_price is not None and m["input_usd_per_m"] > max_input_price:
            continue
        if min_context is not None and m["context"] < min_context:
            continue
        if providers and m["provider"] not in [p.lower() for p in providers]:
            continue
        if modalities:
            required = set(mod.lower() for mod in modalities)
            if not required.issubset(set(m["modalities"])):
                continue
        if use_case:
            uc = use_case.lower()
            # Simple keyword matching against strengths
            keywords = {
                "coding": ["coding", "code"],
                "reasoning": ["reasoning", "math"],
                "writing": ["writing", "summarization"],
                "vision": ["vision", "multimodal"],
                "long context": ["long context", "1M context", "2M context", "10M context"],
                "cheap": ["cheap", "efficient", "fast"],
                "agentic": ["agentic", "tool use", "function calling"],
                "multilingual": ["multilingual"],
                "eu compliant": ["EU-hosted", "EU residency"],
                "real-time": ["real-time"],
                "open source": ["open weights"],
            }.get(uc, [uc])
            if not any(kw.lower() in " ".join(m["strengths"]).lower() for kw in keywords):
                continue
        results.append(m)
    return results


def _estimate_cost(model: dict, input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1_000_000) * model["input_usd_per_m"]
        + (output_tokens / 1_000_000) * model["output_usd_per_m"]
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_compare_models",
        description=(
            "Compare 25+ LLM models across 8 major providers (OpenAI, Anthropic, "
            "Google, Meta, Mistral, xAI, DeepSeek, Cohere, NVIDIA) by price, "
            "context window, capabilities, and modalities. "
            "Optionally estimate cost for a specific workload (input/output token counts). "
            "Filter by use case (coding, reasoning, vision, long context, cheap, agentic, "
            "multilingual, EU compliant, real-time, open source). "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_compare_models(
        use_case: Annotated[Optional[str], Field(description="Filter by use case: coding, reasoning, writing, vision, long context, cheap, agentic, multilingual, EU compliant, real-time, open source")] = None,
        max_input_price_per_m: Annotated[Optional[float], Field(description="Maximum input price in USD per 1M tokens")] = None,
        min_context: Annotated[Optional[int], Field(description="Minimum context window in tokens")] = None,
        providers: Annotated[Optional[List[str]], Field(description="Filter by providers (list of provider names)")] = None,
        modalities: Annotated[Optional[List[str]], Field(description="Required modalities (e.g. ['text','vision'])")] = None,
        estimate_input_tokens: Annotated[Optional[int], Field(description="For cost estimation: number of input tokens")] = None,
        estimate_output_tokens: Annotated[Optional[int], Field(description="For cost estimation: number of output tokens")] = None,
    ) -> str:
        matches = _filter_catalog(use_case, max_input_price_per_m, min_context, providers, modalities)

        # Sort by value: (input + output)/2 ascending
        matches.sort(key=lambda m: (m["input_usd_per_m"] + m["output_usd_per_m"]) / 2)

        # Optional cost estimation
        if estimate_input_tokens and estimate_output_tokens:
            for m in matches:
                m["estimated_cost_usd"] = round(_estimate_cost(m, estimate_input_tokens, estimate_output_tokens), 6)

        result = {
            "matches": matches,
            "matches_count": len(matches),
            "catalog_size": len(_CATALOG),
            "filters_applied": {
                "use_case": use_case,
                "max_input_price_per_m": max_input_price_per_m,
                "min_context": min_context,
                "providers": providers,
                "modalities": modalities,
            },
            "cost_estimation": (
                {"input_tokens": estimate_input_tokens, "output_tokens": estimate_output_tokens}
                if estimate_input_tokens and estimate_output_tokens else None
            ),
            "catalog_version": "2026-04",
            "data_updated": "2026-04-16",
            "disclaimer": (
                "Prices and capabilities change frequently. Always verify on provider pricing pages. "
                "ThinkNEO maintains this catalog as a reference for architectural decisions."
            ),
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "generated_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
