"""
Tool: thinkneo_evaluate_guardrail
Evaluates a prompt or text against ThinkNEO guardrail policies.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..plans import require_plan
from ._common import evaluate_guardrails, utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_evaluate_guardrail",
        description=(
            "Evaluate a prompt or text against ThinkNEO guardrail policies before "
            "sending it to an AI provider. Returns risk assessment, violations found, "
            "and recommendations. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_evaluate_guardrail(
        text: Annotated[str, Field(description="The prompt or text content to evaluate for policy violations (max 32,000 characters)")],
        workspace: Annotated[str, Field(description="Workspace whose guardrail policies to apply for this evaluation")],
        guardrail_mode: Annotated[str, Field(description="Evaluation mode: 'monitor' (log violations only) or 'enforce' (block the request on violation)")] = "monitor",
    ) -> str:
        require_plan("pro")
        workspace = validate_workspace(workspace)

        if guardrail_mode not in ("monitor", "enforce"):
            guardrail_mode = "monitor"

        # Truncate to reasonable evaluation length
        text_to_eval = text[:32_000]

        evaluation = evaluate_guardrails(text_to_eval, workspace)

        # In enforce mode, indicate whether the request would be blocked
        if guardrail_mode == "enforce":
            evaluation["action"] = (
                "BLOCKED" if evaluation["status"] == "BLOCKED" else "ALLOWED"
            )
        else:
            evaluation["action"] = "LOGGED"

        result = {
            "workspace": workspace,
            "guardrail_mode": guardrail_mode,
            "text_length": len(text_to_eval),
            **evaluation,
            "rules_evaluated": 4,
            "evaluation_time_ms": 1,
            "policy_version": "2026-01-01",
            "dashboard_url": f"https://thinkneo.ai/workspaces/{workspace}/guardrails",
        }

        return json.dumps(result, indent=2)
