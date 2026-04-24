"""
Tool: thinkneo_route_model
Intelligent model routing — picks the cheapest model meeting quality requirements.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import get_bearer_token, require_auth
from ..database import hash_key
from ..smart_router import (
    TASK_TYPES,
    log_routed_request,
    route_model,
)
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_route_model",
        description=(
            "AI Smart Router — find the cheapest model that meets your quality threshold. "
            "Specify your task type and quality requirements, and ThinkNEO will recommend "
            "the optimal model with estimated cost and savings vs premium models. "
            "Supports 17+ models across Anthropic, OpenAI, Google, Meta, Mistral, DeepSeek, "
            "Alibaba, Cohere, and xAI. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_route_model(
        task_type: Annotated[str, Field(
            description=(
                "The type of AI task: summarization, classification, code_generation, "
                "chat, analysis, translation, or embedding"
            )
        )],
        quality_threshold: Annotated[int, Field(
            description="Minimum quality score required (0-100). Default 85 = enterprise-grade."
        )] = 85,
        max_latency_ms: Annotated[Optional[int], Field(
            description="Maximum acceptable latency in milliseconds. Omit for no limit."
        )] = None,
        budget_per_request: Annotated[Optional[float], Field(
            description="Maximum budget per request in USD. Omit for no limit."
        )] = None,
        preferred_providers: Annotated[Optional[str], Field(
            description=(
                "Comma-separated list of preferred providers "
                "(e.g., 'openai,anthropic'). These will be prioritized at similar cost."
            )
        )] = None,
        estimated_tokens: Annotated[int, Field(
            description="Estimated total tokens for the request (input + output). Default 1000."
        )] = 1000,
        text_sample: Annotated[Optional[str], Field(
            description=(
                "Optional sample text for better routing. Helps estimate token count "
                "and task complexity. Max 500 characters."
            )
        )] = None,
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)

        # Parse preferred providers
        pref_list = None
        if preferred_providers:
            pref_list = [p.strip().lower() for p in preferred_providers.split(",") if p.strip()]

        # If text_sample provided, estimate tokens from it
        if text_sample:
            # Rough estimation: ~4 chars per token, plus expected output
            sample_tokens = len(text_sample[:500]) // 4
            if sample_tokens > estimated_tokens:
                estimated_tokens = sample_tokens + (sample_tokens // 2)  # add expected output

        # Route
        result = route_model(
            task_type=task_type,
            quality_threshold=quality_threshold,
            max_latency_ms=max_latency_ms,
            preferred_providers=pref_list,
            budget_per_request=budget_per_request,
            estimated_tokens=estimated_tokens,
        )

        # Log the routed request
        log_routed_request(
            key_hash=key_h,
            task_type=task_type,
            model_requested=None,
            model_used=result["recommended_model"],
            provider=result["provider"],
            cost_original=result["original_cost_usd"],
            cost_actual=result["cost_estimate_usd"],
            quality_score=result["quality_score"],
            input_tokens=int(estimated_tokens * 0.7),
            output_tokens=int(estimated_tokens * 0.3),
        )

        result["routed_at"] = utcnow()
        result["note"] = (
            "Use this model for optimal cost/quality balance. "
            "ThinkNEO tracks your savings automatically."
        )

        return json.dumps(result, indent=2)
