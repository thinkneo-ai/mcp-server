"""
Tool: thinkneo_simulate_savings
Free lead-generation tool — shows prospects how much they'd save with Smart Router.
No authentication required.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..smart_router import simulate_savings
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_simulate_savings",
        description=(
            "Simulate how much your organization would save on AI costs using "
            "ThinkNEO Smart Router. Enter your current monthly AI spend and primary model, "
            "and see estimated monthly and annual savings with a recommended model mix. "
            "No authentication required — try it now!"
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_simulate_savings(
        monthly_ai_spend: Annotated[float, Field(
            description="Your current monthly AI API spend in USD (e.g., 5000.00)"
        )],
        primary_model: Annotated[str, Field(
            description=(
                "Your primary model: 'gpt-4o', 'claude-opus-4', 'claude-sonnet-4', "
                "'gpt-4.1', or 'gemini-2.5-pro'"
            )
        )] = "gpt-4o",
        task_distribution: Annotated[Optional[str], Field(
            description=(
                "JSON string of task distribution, e.g., "
                "'{\"chat\": 0.3, \"summarization\": 0.2, \"code_generation\": 0.2, "
                "\"classification\": 0.15, \"analysis\": 0.1, \"translation\": 0.05}'. "
                "Values should sum to ~1.0. Omit for default enterprise distribution."
            )
        )] = None,
    ) -> str:
        # Validate spend
        if monthly_ai_spend <= 0:
            return json.dumps({
                "error": "monthly_ai_spend must be positive",
                "example": "Try monthly_ai_spend=5000 for a $5,000/month spend estimate",
            }, indent=2)

        if monthly_ai_spend > 10_000_000:
            monthly_ai_spend = 10_000_000  # cap at $10M

        # Parse task distribution if provided
        dist = None
        if task_distribution:
            try:
                dist = json.loads(task_distribution)
                if not isinstance(dist, dict):
                    dist = None
            except (json.JSONDecodeError, TypeError):
                dist = None

        result = simulate_savings(
            monthly_ai_spend=monthly_ai_spend,
            primary_model=primary_model,
            task_distribution=dist,
        )

        result["simulated_at"] = utcnow()

        return json.dumps(result, indent=2)
