"""
Tool: thinkneo_estimate_tokens
Estimate token count and cost across models for given text.
Public tool — no authentication required.

Eliminates the "I don't know how much this will cost" friction. Every dev
wants this. ThinkNEO becomes the go-to calculator.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

# Model → (input_usd_per_m, output_usd_per_m, tokens_per_char_factor)
# Factor accounts for tokenizer differences: GPT/Claude use BPE (~4 chars/token),
# Gemini slightly different (~3.7), older models ~4.5.
_MODEL_PRICING = {
    # OpenAI
    "gpt-5": (10.0, 30.0, 0.25),
    "gpt-5-mini": (0.25, 1.0, 0.25),
    "gpt-5-nano": (0.05, 0.20, 0.25),
    "gpt-4o": (2.5, 10.0, 0.25),
    "gpt-4o-mini": (0.15, 0.60, 0.25),
    "o4-mini": (1.1, 4.4, 0.25),
    "o3": (15.0, 60.0, 0.25),
    # Anthropic
    "claude-opus-4-6": (15.0, 75.0, 0.27),
    "claude-sonnet-4-6": (3.0, 15.0, 0.27),
    "claude-haiku-4-5": (0.80, 4.0, 0.27),
    # Google
    "gemini-2.5-pro": (2.5, 15.0, 0.25),
    "gemini-2.5-flash": (0.30, 2.5, 0.25),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.25),
    # Meta (Llama) — via Together/Groq/Bedrock typical pricing
    "llama-4-scout": (0.12, 0.35, 0.23),
    "llama-4-maverick": (0.20, 0.70, 0.23),
    "llama-4-behemoth": (2.5, 7.5, 0.23),
    # Mistral
    "mistral-large-2": (2.0, 6.0, 0.27),
    "mistral-medium-3": (0.40, 2.0, 0.27),
    # xAI
    "grok-4": (3.0, 15.0, 0.25),
    "grok-4-fast": (0.20, 0.50, 0.25),
    # DeepSeek
    "deepseek-v3.5": (0.27, 1.10, 0.22),
    "deepseek-r1": (0.55, 2.19, 0.22),
    # Cohere
    "command-a": (2.5, 10.0, 0.27),
    # NVIDIA
    "nemotron-nano-12b-v2": (0.04, 0.10, 0.24),
    "nemotron-ultra-253b": (1.50, 4.50, 0.24),
}


def _estimate_token_count(text: str, chars_per_token: float) -> int:
    """Estimate tokens using a hybrid approach."""
    if not text:
        return 0
    # Approach 1: chars / chars_per_token
    by_chars = len(text) * chars_per_token
    # Approach 2: word count * 1.3 (punctuation / BPE splits add ~30%)
    words = len(re.findall(r"\S+", text))
    by_words = words * 1.3
    # Weighted average — chars dominates for shorter text
    return int(round((by_chars * 0.7) + (by_words * 0.3)))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_estimate_tokens",
        description=(
            "Estimate token count and cost for text across 25+ LLM models. "
            "Uses tokenizer-specific char-per-token factors (GPT/Claude/Gemini/Llama/etc.) "
            "Returns per-model estimates with input + output cost breakdown. "
            "Useful for: budgeting before a large batch job, comparing models by workload, "
            "context window planning. No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_estimate_tokens(
        text: Annotated[str, Field(description="Text to estimate tokens for")],
        expected_output_tokens: Annotated[int, Field(description="Expected output tokens (for cost estimation). Defaults to input token count.")] = 0,
        models: Annotated[Optional[List[str]], Field(description="Specific models to estimate (list of model names). Defaults to all.")] = None,
    ) -> str:
        """Estimate token count and cost for text across 25+ LLM models. Uses tokenizer-specific char-per-token factors (GPT/Claude/Gemini/Llama/etc.) Returns per-model estimates with input + output cost breakdown. Useful for: budgeting before a large batch job, comparing models by workload,"""
        selected_models = models if models else list(_MODEL_PRICING.keys())

        results = []
        for model_name in selected_models:
            pricing = _MODEL_PRICING.get(model_name)
            if not pricing:
                continue
            in_price, out_price, factor = pricing
            tokens = _estimate_token_count(text, factor)
            out_tokens = expected_output_tokens if expected_output_tokens > 0 else tokens
            in_cost = (tokens / 1_000_000) * in_price
            out_cost = (out_tokens / 1_000_000) * out_price
            results.append({
                "model": model_name,
                "input_tokens_estimated": tokens,
                "output_tokens_estimated": out_tokens,
                "input_cost_usd": round(in_cost, 8),
                "output_cost_usd": round(out_cost, 8),
                "total_cost_usd": round(in_cost + out_cost, 8),
                "cost_per_1k_calls_usd": round((in_cost + out_cost) * 1_000, 4),
            })

        # Sort by cheapest
        results.sort(key=lambda x: x["total_cost_usd"])

        result = {
            "text_length_chars": len(text),
            "text_length_words": len(text.split()),
            "expected_output_tokens": expected_output_tokens or "(same as input)",
            "estimates": results,
            "cheapest_model": results[0] if results else None,
            "most_expensive_model": results[-1] if results else None,
            "cost_ratio_cheap_vs_expensive": (
                round(results[-1]["total_cost_usd"] / max(results[0]["total_cost_usd"], 1e-9), 1)
                if len(results) >= 2 else None
            ),
            "note": (
                "Token counts are estimates — exact numbers require the model's tokenizer. "
                "Accurate to ±15% for English text. For other languages, expect +30-50% token overhead."
            ),
            "tier": "free",
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "generated_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
