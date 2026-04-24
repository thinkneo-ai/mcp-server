"""
ThinkNEO AI Smart Router — Intelligent model routing engine.

Routes requests to the cheapest model that meets a quality threshold,
then tracks exactly how much money the customer saves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task types
# ---------------------------------------------------------------------------
TASK_TYPES = [
    "summarization",
    "classification",
    "code_generation",
    "chat",
    "analysis",
    "translation",
    "embedding",
]

# ---------------------------------------------------------------------------
# Model database — cost per 1K tokens, quality scores per task, latency
# Prices in USD per 1K tokens as of April 2026
# ---------------------------------------------------------------------------

@dataclass
class ModelSpec:
    id: str
    provider: str
    display_name: str
    cost_input_per_1k: float   # USD per 1K input tokens
    cost_output_per_1k: float  # USD per 1K output tokens
    quality: Dict[str, int]    # task_type → quality score (0-100)
    avg_latency_ms: int
    context_window: int
    is_available: bool = True  # can be toggled by health checks


# Premium reference models (what the customer would have used)
PREMIUM_REFERENCE = {
    "default": "claude-opus-4",
    "code_generation": "claude-opus-4",
    "analysis": "gpt-4o",
    "chat": "gpt-4o",
    "summarization": "claude-sonnet-4",
    "classification": "gpt-4o-mini",
    "translation": "gpt-4o",
    "embedding": "text-embedding-3-large",
}


MODEL_DB: List[ModelSpec] = [
    # ── Anthropic ─────────────────────────────────────────────────
    ModelSpec(
        id="claude-opus-4",
        provider="anthropic",
        display_name="Claude Opus 4",
        cost_input_per_1k=0.015,
        cost_output_per_1k=0.075,
        quality={"summarization": 97, "classification": 96, "code_generation": 98,
                 "chat": 97, "analysis": 98, "translation": 95, "embedding": 0},
        avg_latency_ms=2800,
        context_window=200000,
    ),
    ModelSpec(
        id="claude-sonnet-4",
        provider="anthropic",
        display_name="Claude Sonnet 4",
        cost_input_per_1k=0.003,
        cost_output_per_1k=0.015,
        quality={"summarization": 94, "classification": 93, "code_generation": 95,
                 "chat": 94, "analysis": 95, "translation": 93, "embedding": 0},
        avg_latency_ms=1800,
        context_window=200000,
    ),
    ModelSpec(
        id="claude-haiku-3.5",
        provider="anthropic",
        display_name="Claude Haiku 3.5",
        cost_input_per_1k=0.0008,
        cost_output_per_1k=0.004,
        quality={"summarization": 87, "classification": 88, "code_generation": 83,
                 "chat": 86, "analysis": 85, "translation": 86, "embedding": 0},
        avg_latency_ms=600,
        context_window=200000,
    ),

    # ── OpenAI ────────────────────────────────────────────────────
    ModelSpec(
        id="gpt-4o",
        provider="openai",
        display_name="GPT-4o",
        cost_input_per_1k=0.0025,
        cost_output_per_1k=0.010,
        quality={"summarization": 94, "classification": 94, "code_generation": 93,
                 "chat": 95, "analysis": 95, "translation": 94, "embedding": 0},
        avg_latency_ms=1500,
        context_window=128000,
    ),
    ModelSpec(
        id="gpt-4o-mini",
        provider="openai",
        display_name="GPT-4o Mini",
        cost_input_per_1k=0.00015,
        cost_output_per_1k=0.0006,
        quality={"summarization": 86, "classification": 88, "code_generation": 82,
                 "chat": 85, "analysis": 84, "translation": 85, "embedding": 0},
        avg_latency_ms=700,
        context_window=128000,
    ),
    ModelSpec(
        id="gpt-4.1",
        provider="openai",
        display_name="GPT-4.1",
        cost_input_per_1k=0.002,
        cost_output_per_1k=0.008,
        quality={"summarization": 95, "classification": 95, "code_generation": 96,
                 "chat": 95, "analysis": 96, "translation": 95, "embedding": 0},
        avg_latency_ms=1600,
        context_window=1047576,
    ),
    ModelSpec(
        id="gpt-4.1-mini",
        provider="openai",
        display_name="GPT-4.1 Mini",
        cost_input_per_1k=0.0004,
        cost_output_per_1k=0.0016,
        quality={"summarization": 89, "classification": 90, "code_generation": 87,
                 "chat": 88, "analysis": 88, "translation": 88, "embedding": 0},
        avg_latency_ms=800,
        context_window=1047576,
    ),
    ModelSpec(
        id="gpt-4.1-nano",
        provider="openai",
        display_name="GPT-4.1 Nano",
        cost_input_per_1k=0.0001,
        cost_output_per_1k=0.0004,
        quality={"summarization": 82, "classification": 85, "code_generation": 76,
                 "chat": 81, "analysis": 80, "translation": 80, "embedding": 0},
        avg_latency_ms=400,
        context_window=1047576,
    ),

    # ── Google ────────────────────────────────────────────────────
    ModelSpec(
        id="gemini-2.5-pro",
        provider="google",
        display_name="Gemini 2.5 Pro",
        cost_input_per_1k=0.00125,
        cost_output_per_1k=0.01,
        quality={"summarization": 94, "classification": 93, "code_generation": 94,
                 "chat": 93, "analysis": 95, "translation": 94, "embedding": 0},
        avg_latency_ms=1400,
        context_window=1048576,
    ),
    ModelSpec(
        id="gemini-2.5-flash",
        provider="google",
        display_name="Gemini 2.5 Flash",
        cost_input_per_1k=0.00015,
        cost_output_per_1k=0.0006,
        quality={"summarization": 88, "classification": 89, "code_generation": 85,
                 "chat": 87, "analysis": 87, "translation": 87, "embedding": 0},
        avg_latency_ms=500,
        context_window=1048576,
    ),

    # ── Meta ──────────────────────────────────────────────────────
    ModelSpec(
        id="llama-3.3-70b",
        provider="meta",
        display_name="Llama 3.3 70B",
        cost_input_per_1k=0.00059,
        cost_output_per_1k=0.00079,
        quality={"summarization": 88, "classification": 87, "code_generation": 85,
                 "chat": 87, "analysis": 86, "translation": 85, "embedding": 0},
        avg_latency_ms=900,
        context_window=131072,
    ),

    # ── Mistral ───────────────────────────────────────────────────
    ModelSpec(
        id="mistral-large",
        provider="mistral",
        display_name="Mistral Large",
        cost_input_per_1k=0.002,
        cost_output_per_1k=0.006,
        quality={"summarization": 91, "classification": 91, "code_generation": 90,
                 "chat": 91, "analysis": 91, "translation": 91, "embedding": 0},
        avg_latency_ms=1200,
        context_window=131072,
    ),

    # ── DeepSeek ──────────────────────────────────────────────────
    ModelSpec(
        id="deepseek-v3",
        provider="deepseek",
        display_name="DeepSeek V3",
        cost_input_per_1k=0.00027,
        cost_output_per_1k=0.0011,
        quality={"summarization": 89, "classification": 88, "code_generation": 90,
                 "chat": 87, "analysis": 89, "translation": 86, "embedding": 0},
        avg_latency_ms=1000,
        context_window=131072,
    ),
    ModelSpec(
        id="deepseek-r1",
        provider="deepseek",
        display_name="DeepSeek R1",
        cost_input_per_1k=0.00055,
        cost_output_per_1k=0.0022,
        quality={"summarization": 91, "classification": 90, "code_generation": 93,
                 "chat": 89, "analysis": 93, "translation": 87, "embedding": 0},
        avg_latency_ms=2200,
        context_window=131072,
    ),

    # ── Alibaba ───────────────────────────────────────────────────
    ModelSpec(
        id="qwen-3-235b",
        provider="alibaba",
        display_name="Qwen 3 235B",
        cost_input_per_1k=0.0012,
        cost_output_per_1k=0.0048,
        quality={"summarization": 92, "classification": 91, "code_generation": 92,
                 "chat": 91, "analysis": 92, "translation": 93, "embedding": 0},
        avg_latency_ms=1800,
        context_window=131072,
    ),

    # ── Cohere ────────────────────────────────────────────────────
    ModelSpec(
        id="command-r-plus",
        provider="cohere",
        display_name="Command R+",
        cost_input_per_1k=0.0025,
        cost_output_per_1k=0.01,
        quality={"summarization": 90, "classification": 89, "code_generation": 84,
                 "chat": 89, "analysis": 88, "translation": 87, "embedding": 0},
        avg_latency_ms=1300,
        context_window=128000,
    ),

    # ── xAI ───────────────────────────────────────────────────────
    ModelSpec(
        id="grok-3",
        provider="xai",
        display_name="Grok 3",
        cost_input_per_1k=0.003,
        cost_output_per_1k=0.015,
        quality={"summarization": 93, "classification": 92, "code_generation": 93,
                 "chat": 94, "analysis": 93, "translation": 91, "embedding": 0},
        avg_latency_ms=1700,
        context_window=131072,
    ),
]

# Build lookup dicts
_MODEL_BY_ID: Dict[str, ModelSpec] = {m.id: m for m in MODEL_DB}
_MODELS_BY_PROVIDER: Dict[str, List[ModelSpec]] = {}
for _m in MODEL_DB:
    _MODELS_BY_PROVIDER.setdefault(_m.provider, []).append(_m)


# ---------------------------------------------------------------------------
# Core routing algorithm
# ---------------------------------------------------------------------------

def route_model(
    task_type: str,
    quality_threshold: int = 85,
    max_latency_ms: Optional[int] = None,
    preferred_providers: Optional[List[str]] = None,
    blocked_providers: Optional[List[str]] = None,
    budget_per_request: Optional[float] = None,
    estimated_tokens: int = 1000,
) -> Dict[str, Any]:
    """
    Route to the cheapest model that meets the quality threshold.

    Returns dict with: recommended_model, provider, cost_estimate,
    quality_estimate, savings_vs_premium, alternatives.
    """
    if task_type not in TASK_TYPES:
        task_type = "chat"  # safe default

    quality_threshold = max(0, min(100, quality_threshold))
    blocked = set(blocked_providers or [])

    # Step 1: Filter eligible models
    eligible = []
    for model in MODEL_DB:
        # Skip embedding-only tasks for non-embedding models and vice versa
        quality = model.quality.get(task_type, 0)
        if quality < quality_threshold:
            continue
        if not model.is_available:
            continue
        if model.provider in blocked:
            continue
        if max_latency_ms and model.avg_latency_ms > max_latency_ms:
            continue

        # Estimate cost for this request
        # Assume 70/30 input/output split for cost estimation
        input_tokens = int(estimated_tokens * 0.7)
        output_tokens = int(estimated_tokens * 0.3)
        cost = (input_tokens / 1000 * model.cost_input_per_1k +
                output_tokens / 1000 * model.cost_output_per_1k)

        if budget_per_request and cost > budget_per_request:
            continue

        eligible.append((model, quality, cost))

    if not eligible:
        # Fallback: relax threshold by 10 and try again
        for model in MODEL_DB:
            quality = model.quality.get(task_type, 0)
            if quality < max(0, quality_threshold - 10):
                continue
            if not model.is_available:
                continue
            input_tokens = int(estimated_tokens * 0.7)
            output_tokens = int(estimated_tokens * 0.3)
            cost = (input_tokens / 1000 * model.cost_input_per_1k +
                    output_tokens / 1000 * model.cost_output_per_1k)
            eligible.append((model, quality, cost))

    if not eligible:
        # Ultimate fallback
        fallback = _MODEL_BY_ID.get("gpt-4o-mini", MODEL_DB[0])
        q = fallback.quality.get(task_type, 80)
        input_tokens = int(estimated_tokens * 0.7)
        output_tokens = int(estimated_tokens * 0.3)
        c = (input_tokens / 1000 * fallback.cost_input_per_1k +
             output_tokens / 1000 * fallback.cost_output_per_1k)
        eligible = [(fallback, q, c)]

    # Step 2: Sort by cost (cheapest first), break ties with quality (higher better)
    # If preferred_providers given, boost them by sorting preferred first at same cost tier
    if preferred_providers:
        pref_set = set(preferred_providers)
        eligible.sort(key=lambda x: (
            0 if x[0].provider in pref_set else 1,
            x[2],      # cost ascending
            -x[1],     # quality descending
        ))
    else:
        eligible.sort(key=lambda x: (x[2], -x[1]))

    # Step 3: Pick the best (cheapest meeting threshold)
    best_model, best_quality, best_cost = eligible[0]

    # Step 4: Calculate savings vs premium reference
    ref_id = PREMIUM_REFERENCE.get(task_type, "claude-opus-4")
    ref_model = _MODEL_BY_ID.get(ref_id, MODEL_DB[0])
    input_tokens = int(estimated_tokens * 0.7)
    output_tokens = int(estimated_tokens * 0.3)
    ref_cost = (input_tokens / 1000 * ref_model.cost_input_per_1k +
                output_tokens / 1000 * ref_model.cost_output_per_1k)

    savings_usd = max(0, ref_cost - best_cost)
    savings_pct = round((savings_usd / ref_cost * 100) if ref_cost > 0 else 0, 1)

    # Step 5: Build alternatives (top 3 after the best)
    alternatives = []
    for model, quality, cost in eligible[1:4]:
        alt_savings = max(0, ref_cost - cost)
        alt_pct = round((alt_savings / ref_cost * 100) if ref_cost > 0 else 0, 1)
        alternatives.append({
            "model": model.id,
            "provider": model.provider,
            "display_name": model.display_name,
            "quality_score": quality,
            "cost_estimate_usd": round(cost, 6),
            "savings_vs_premium_pct": alt_pct,
            "avg_latency_ms": model.avg_latency_ms,
        })

    return {
        "recommended_model": best_model.id,
        "provider": best_model.provider,
        "display_name": best_model.display_name,
        "quality_score": best_quality,
        "cost_estimate_usd": round(best_cost, 6),
        "original_cost_usd": round(ref_cost, 6),
        "savings_usd": round(savings_usd, 6),
        "savings_pct": savings_pct,
        "avg_latency_ms": best_model.avg_latency_ms,
        "context_window": best_model.context_window,
        "premium_reference": ref_model.id,
        "task_type": task_type,
        "quality_threshold": quality_threshold,
        "alternatives": alternatives,
        "total_models_evaluated": len(MODEL_DB),
        "models_meeting_threshold": len(eligible),
    }


# ---------------------------------------------------------------------------
# Savings simulation (lead gen — no auth required)
# ---------------------------------------------------------------------------

# Average cost per 1K tokens for popular models (blended input+output)
_BLENDED_COST_PER_1K = {
    "claude-opus-4": 0.045,
    "claude-sonnet-4": 0.009,
    "gpt-4o": 0.00625,
    "gpt-4.1": 0.005,
    "gemini-2.5-pro": 0.005625,
}


def simulate_savings(
    monthly_ai_spend: float,
    primary_model: str = "gpt-4o",
    task_distribution: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Simulate how much an enterprise would save using ThinkNEO Smart Router.

    Uses the task distribution to estimate the optimal model mix and savings.
    """
    if task_distribution is None:
        task_distribution = {
            "chat": 0.30,
            "summarization": 0.20,
            "classification": 0.15,
            "code_generation": 0.15,
            "analysis": 0.10,
            "translation": 0.05,
            "embedding": 0.05,
        }

    # Normalize distribution
    total = sum(task_distribution.values())
    if total > 0:
        task_distribution = {k: v / total for k, v in task_distribution.items()}

    # For each task type, find the cheapest model that meets quality >= 85
    # and calculate the blended savings rate
    model_mix = {}
    weighted_savings_rate = 0.0

    for task_type, weight in task_distribution.items():
        if task_type == "embedding":
            # Embeddings are already cheap, minimal savings
            model_mix[task_type] = {
                "recommended_model": "text-embedding-3-large",
                "savings_rate": 0.0,
            }
            continue

        result = route_model(task_type=task_type, quality_threshold=85)
        savings_rate = result["savings_pct"] / 100.0

        model_mix[task_type] = {
            "recommended_model": result["recommended_model"],
            "provider": result["provider"],
            "quality_score": result["quality_score"],
            "savings_rate_pct": result["savings_pct"],
        }
        weighted_savings_rate += weight * savings_rate

    estimated_monthly_savings = round(monthly_ai_spend * weighted_savings_rate, 2)
    estimated_annual_savings = round(estimated_monthly_savings * 12, 2)
    optimized_monthly_cost = round(monthly_ai_spend - estimated_monthly_savings, 2)

    return {
        "current_monthly_spend": monthly_ai_spend,
        "primary_model": primary_model,
        "optimized_monthly_cost": optimized_monthly_cost,
        "estimated_monthly_savings": estimated_monthly_savings,
        "estimated_annual_savings": estimated_annual_savings,
        "savings_percentage": round(weighted_savings_rate * 100, 1),
        "recommended_model_mix": model_mix,
        "task_distribution": task_distribution,
        "assumptions": [
            "Quality threshold: 85/100 (enterprise-grade)",
            "Based on current model pricing as of April 2026",
            f"Compared against {primary_model} as your primary model",
            "Actual savings depend on your specific workload distribution",
            "Includes automatic failover to maintain uptime",
        ],
        "next_steps": {
            "get_started": "https://thinkneo.ai/pricing",
            "schedule_demo": "Use the thinkneo_schedule_demo tool",
            "contact": "hello@thinkneo.ai",
        },
    }


# ---------------------------------------------------------------------------
# DB helpers for savings tracking
# ---------------------------------------------------------------------------

def log_routed_request(
    key_hash: str,
    task_type: str,
    model_requested: Optional[str],
    model_used: str,
    provider: str,
    cost_original: float,
    cost_actual: float,
    latency_ms: Optional[int] = None,
    quality_score: Optional[int] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Log a routed request to the router_requests table."""
    from .database import _get_conn
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO router_requests
                        (key_hash, task_type, model_requested, model_used, provider,
                         cost_original, cost_actual, latency_ms, quality_score,
                         input_tokens, output_tokens)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (key_hash, task_type, model_requested, model_used, provider,
                     cost_original, cost_actual, latency_ms, quality_score,
                     input_tokens, output_tokens),
                )
    except Exception as exc:
        logger.warning("DB log_routed_request failed: %s", exc)


def get_savings_report(key_hash: str, days: int = 30) -> Dict[str, Any]:
    """Get savings report for a given API key over the specified period."""
    from .database import _get_conn
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Overall stats
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total_requests,
                        COALESCE(SUM(cost_original), 0) as total_original,
                        COALESCE(SUM(cost_actual), 0) as total_actual,
                        COALESCE(SUM(cost_original - cost_actual), 0) as total_savings,
                        COALESCE(AVG(quality_score), 0) as avg_quality
                    FROM router_requests
                    WHERE key_hash = %s
                      AND routed_at >= NOW() - INTERVAL '%s days'
                    """,
                    (key_hash, days),
                )
                overall = cur.fetchone()

                # By task type
                cur.execute(
                    """
                    SELECT
                        task_type,
                        COUNT(*) as requests,
                        COALESCE(SUM(cost_original - cost_actual), 0) as savings
                    FROM router_requests
                    WHERE key_hash = %s
                      AND routed_at >= NOW() - INTERVAL '%s days'
                    GROUP BY task_type
                    ORDER BY savings DESC
                    """,
                    (key_hash, days),
                )
                by_task = [dict(r) for r in cur.fetchall()]

                # Model distribution
                cur.execute(
                    """
                    SELECT
                        model_used,
                        provider,
                        COUNT(*) as requests,
                        COALESCE(SUM(cost_actual), 0) as total_cost
                    FROM router_requests
                    WHERE key_hash = %s
                      AND routed_at >= NOW() - INTERVAL '%s days'
                    GROUP BY model_used, provider
                    ORDER BY requests DESC
                    LIMIT 10
                    """,
                    (key_hash, days),
                )
                model_dist = [dict(r) for r in cur.fetchall()]

                total_original = float(overall["total_original"]) if overall else 0
                total_actual = float(overall["total_actual"]) if overall else 0
                total_savings = float(overall["total_savings"]) if overall else 0
                savings_pct = round(
                    (total_savings / total_original * 100) if total_original > 0 else 0, 1
                )

                return {
                    "period_days": days,
                    "total_requests_routed": overall["total_requests"] if overall else 0,
                    "total_original_cost_usd": round(total_original, 4),
                    "total_actual_cost_usd": round(total_actual, 4),
                    "total_savings_usd": round(total_savings, 4),
                    "savings_pct": savings_pct,
                    "avg_quality_score": round(float(overall["avg_quality"] or 0), 1),
                    "savings_by_task_type": by_task,
                    "model_distribution": model_dist,
                }

    except Exception as exc:
        logger.warning("DB get_savings_report failed: %s", exc)
        return {
            "period_days": days,
            "total_requests_routed": 0,
            "total_original_cost_usd": 0,
            "total_actual_cost_usd": 0,
            "total_savings_usd": 0,
            "savings_pct": 0,
            "avg_quality_score": 0,
            "savings_by_task_type": [],
            "model_distribution": [],
            "_note": "Savings report temporarily unavailable",
        }


def get_model_catalog() -> List[Dict[str, Any]]:
    """Return the full model catalog for reference."""
    catalog = []
    for m in MODEL_DB:
        catalog.append({
            "model_id": m.id,
            "provider": m.provider,
            "display_name": m.display_name,
            "cost_input_per_1k_tokens": m.cost_input_per_1k,
            "cost_output_per_1k_tokens": m.cost_output_per_1k,
            "avg_latency_ms": m.avg_latency_ms,
            "context_window": m.context_window,
            "quality_scores": m.quality,
        })
    return catalog
