"""
Prompt Caching FinOps Tracker.

Tracks cached vs uncached tokens per provider/model and calculates cost savings.

Supported providers:
- Anthropic: cache_creation_input_tokens, cache_read_input_tokens
- OpenAI: cached_tokens in usage.prompt_tokens_details

Pricing (per 1K tokens, as of April 2026):
- Anthropic cache write: same as input (no extra cost to create)
- Anthropic cache read: 90% discount vs input
- OpenAI cached: 50% discount vs input
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache pricing: discount factor vs base input price
CACHE_PRICING = {
    "anthropic": {
        "cache_read_discount": 0.9,   # 90% cheaper than base input
        "cache_write_premium": 1.25,  # 25% more expensive to create cache
    },
    "openai": {
        "cache_read_discount": 0.5,   # 50% cheaper than base input
    },
    "google": {
        "cache_read_discount": 0.75,  # 75% cheaper (context caching)
    },
}

# Base input prices per 1K tokens (April 2026)
BASE_INPUT_PRICES = {
    "claude-opus-4": 0.015,
    "claude-sonnet-4": 0.003,
    "claude-haiku-3.5": 0.0008,
    "gpt-4o": 0.0025,
    "gpt-4o-mini": 0.00015,
    "gpt-4.1": 0.002,
    "gemini-2.5-pro": 0.00125,
    "gemini-2.5-flash": 0.00015,
}


def parse_cache_usage(provider: str, usage_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse cache-related token counts from a provider's usage response.

    Returns dict with:
      - uncached_tokens: tokens charged at full price
      - cached_read_tokens: tokens read from cache (discounted)
      - cached_write_tokens: tokens written to cache
      - total_input_tokens: sum of all input tokens
    """
    result = {
        "uncached_tokens": 0,
        "cached_read_tokens": 0,
        "cached_write_tokens": 0,
        "total_input_tokens": 0,
        "provider": provider,
    }

    if provider == "anthropic":
        result["cached_read_tokens"] = usage_data.get("cache_read_input_tokens", 0)
        result["cached_write_tokens"] = usage_data.get("cache_creation_input_tokens", 0)
        total_input = usage_data.get("input_tokens", 0)
        result["total_input_tokens"] = total_input
        result["uncached_tokens"] = max(0, total_input - result["cached_read_tokens"] - result["cached_write_tokens"])

    elif provider == "openai":
        prompt_details = usage_data.get("prompt_tokens_details", {})
        result["cached_read_tokens"] = prompt_details.get("cached_tokens", 0)
        result["total_input_tokens"] = usage_data.get("prompt_tokens", 0)
        result["uncached_tokens"] = max(0, result["total_input_tokens"] - result["cached_read_tokens"])

    elif provider == "google":
        result["cached_read_tokens"] = usage_data.get("cached_content_token_count", 0)
        result["total_input_tokens"] = usage_data.get("prompt_token_count", 0)
        result["uncached_tokens"] = max(0, result["total_input_tokens"] - result["cached_read_tokens"])

    return result


def calculate_cache_savings(
    provider: str,
    model: str,
    cached_read_tokens: int,
    cached_write_tokens: int = 0,
    uncached_tokens: int = 0,
) -> Dict[str, Any]:
    """
    Calculate cost savings from prompt caching.

    Returns dict with cost_without_cache, cost_with_cache, savings_usd, savings_pct.
    """
    base_price = BASE_INPUT_PRICES.get(model, 0.003)  # default to Sonnet pricing
    pricing = CACHE_PRICING.get(provider, {})

    # Cost without caching: all tokens at full price
    total_tokens = uncached_tokens + cached_read_tokens + cached_write_tokens
    cost_without_cache = (total_tokens / 1000) * base_price

    # Cost with caching
    cost_uncached = (uncached_tokens / 1000) * base_price
    read_discount = pricing.get("cache_read_discount", 0.5)
    cost_cached_read = (cached_read_tokens / 1000) * base_price * (1 - read_discount)
    write_premium = pricing.get("cache_write_premium", 1.0)
    cost_cached_write = (cached_write_tokens / 1000) * base_price * write_premium

    cost_with_cache = cost_uncached + cost_cached_read + cost_cached_write

    savings = max(0, cost_without_cache - cost_with_cache)
    savings_pct = round((savings / cost_without_cache * 100) if cost_without_cache > 0 else 0, 1)

    return {
        "cost_without_cache_usd": round(cost_without_cache, 6),
        "cost_with_cache_usd": round(cost_with_cache, 6),
        "savings_usd": round(savings, 6),
        "savings_pct": savings_pct,
        "cache_hit_rate_pct": round(
            (cached_read_tokens / total_tokens * 100) if total_tokens > 0 else 0, 1
        ),
        "model": model,
        "provider": provider,
    }


def generate_cache_savings_report(
    records: List[Dict[str, Any]],
    period: str = "30d",
) -> Dict[str, Any]:
    """
    Generate aggregate cache savings report from a list of request records.

    Each record should have: provider, model, cached_read_tokens, cached_write_tokens, uncached_tokens.
    """
    total_savings = 0.0
    total_cost_without = 0.0
    total_cost_with = 0.0
    total_cached_read = 0
    total_cached_write = 0
    total_uncached = 0
    by_model: Dict[str, Dict[str, float]] = {}

    for r in records:
        calc = calculate_cache_savings(
            provider=r.get("provider", "anthropic"),
            model=r.get("model", "claude-sonnet-4"),
            cached_read_tokens=r.get("cached_read_tokens", 0),
            cached_write_tokens=r.get("cached_write_tokens", 0),
            uncached_tokens=r.get("uncached_tokens", 0),
        )
        total_savings += calc["savings_usd"]
        total_cost_without += calc["cost_without_cache_usd"]
        total_cost_with += calc["cost_with_cache_usd"]
        total_cached_read += r.get("cached_read_tokens", 0)
        total_cached_write += r.get("cached_write_tokens", 0)
        total_uncached += r.get("uncached_tokens", 0)

        model = r.get("model", "unknown")
        if model not in by_model:
            by_model[model] = {"savings": 0, "requests": 0, "cached_reads": 0}
        by_model[model]["savings"] += calc["savings_usd"]
        by_model[model]["requests"] += 1
        by_model[model]["cached_reads"] += r.get("cached_read_tokens", 0)

    total_tokens = total_cached_read + total_cached_write + total_uncached

    return {
        "period": period,
        "total_requests": len(records),
        "total_tokens": total_tokens,
        "cached_read_tokens": total_cached_read,
        "cached_write_tokens": total_cached_write,
        "uncached_tokens": total_uncached,
        "cache_hit_rate_pct": round(
            (total_cached_read / total_tokens * 100) if total_tokens > 0 else 0, 1
        ),
        "cost_without_cache_usd": round(total_cost_without, 4),
        "cost_with_cache_usd": round(total_cost_with, 4),
        "total_savings_usd": round(total_savings, 4),
        "savings_pct": round(
            (total_savings / total_cost_without * 100) if total_cost_without > 0 else 0, 1
        ),
        "by_model": {
            model: {
                "savings_usd": round(data["savings"], 4),
                "requests": data["requests"],
                "cached_read_tokens": data["cached_reads"],
            }
            for model, data in sorted(by_model.items(), key=lambda x: -x[1]["savings"])
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
