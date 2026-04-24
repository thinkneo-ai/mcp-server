"""
Tools: Outcome Benchmarking — Quality-Based Routing

3 MCP tools:
  - thinkneo_benchmark_report: View benchmark matrix
  - thinkneo_benchmark_compare: Side-by-side provider comparison
  - thinkneo_router_explain: Explain routing decision with benchmark data
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth, get_bearer_token
from ..outcome_benchmarking import (
    record_feedback,
    get_benchmark_report,
    compare_benchmarks,
    explain_routing,
)
from .._common_obs import utcnow_obs


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="thinkneo_benchmark_report",
        description=(
            "View the outcome benchmark matrix — real quality scores per provider/model/task_type "
            "based on verified outcomes, not static estimates. Shows verification rates, sample counts, "
            "and rankings. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_benchmark_report(
        task_type: Annotated[Optional[str], Field(
            description="Filter by task type: 'summarization', 'code_generation', 'classification', 'translation', etc. Leave empty for all."
        )] = None,
    ) -> str:
        token = require_auth()
        result = get_benchmark_report(api_key=token, task_type=task_type)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_benchmark_compare",
        description=(
            "Compare providers side-by-side for a specific task type. Shows quality scores, "
            "verification rates, and rankings based on real outcomes. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_benchmark_compare(
        task_type: Annotated[str, Field(
            description="Task type to compare: 'summarization', 'code_generation', 'classification', 'translation', 'analysis', 'chat'"
        )],
        providers: Annotated[Optional[list], Field(
            description="Optional list of providers to compare (e.g., ['anthropic', 'openai']). Leave empty for all."
        )] = None,
    ) -> str:
        token = require_auth()
        prov = providers
        if isinstance(prov, str):
            prov = json.loads(prov)
        result = compare_benchmarks(api_key=token, task_type=task_type, providers=prov)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_router_explain",
        description=(
            "Explain why the Smart Router would choose a specific model for a task type. "
            "Shows both benchmark-based (real outcomes) and static quality estimates, "
            "and explains the reasoning behind the recommendation. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_router_explain(
        task_type: Annotated[str, Field(
            description="Task type: 'summarization', 'code_generation', 'classification', 'translation', 'analysis', 'chat'"
        )],
        quality_threshold: Annotated[int, Field(
            description="Minimum quality score required (0-100, default 85)"
        )] = 85,
    ) -> str:
        token = require_auth()
        result = explain_routing(api_key=token, task_type=task_type, quality_threshold=quality_threshold)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)
