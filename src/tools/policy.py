"""
Tool: thinkneo_check_policy
Returns policy status from the live brain API.
"""
from __future__ import annotations
import json
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow, validate_workspace

def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_check_policy",
        description="Check AI governance policies including model access, budget limits, data controls, and agent governance from the ThinkNEO gateway.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_check_policy(
        workspace: Annotated[str, Field(description="Workspace name or ID")] = "default",
    ) -> str:
        """Check if a specific model, provider, or action is allowed by the governance policies configured for a workspace."""
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()

        result = {"workspace": workspace, "source": "live_gateway", "fetched_at": utcnow()}

        metrics = await brain_get("/v1/internal/runtime-metrics", token=token)
        if not is_error(metrics):
            rm = metrics.get("runtime_metrics", metrics)
            result["policies"] = {
                "compliance_gateway": {"enabled": rm.get("compliance_gateway_enabled"), "mode": rm.get("compliance_gateway_mode")},
                "runtime_guardrails": {"enabled": rm.get("goal2_runtime_guardrails_enabled"), "mode": rm.get("goal2_runtime_guardrails_mode")},
                "data_controls": {"enabled": rm.get("goal3_data_controls_enabled"), "mode": rm.get("goal3_data_controls_mode"), "mask_input": rm.get("goal3_mask_input_enabled"), "mask_output": rm.get("goal3_mask_output_enabled")},
                "governance": {"enabled": rm.get("goal4_governance_enabled"), "mode": rm.get("goal4_governance_mode"), "frameworks": rm.get("goal4_required_frameworks")},
                "agent_governance": {"enabled": rm.get("goal5_agent_governance_enabled"), "mode": rm.get("goal5_agent_governance_mode"), "require_approval": rm.get("goal5_require_approval_for_agents")},
                "finops": {"enabled": rm.get("goal7_finops_accountability_enabled"), "spend_control_ratio": rm.get("goal6_default_spend_control_ratio")},
                "rate_limiting": {"enabled": rm.get("gateway_rate_limit_enabled"), "requests_per_minute": rm.get("gateway_rate_limit_requests_per_window")},
            }
            result["enforcement_stats"] = {
                "requests_total": rm.get("requests_total", 0),
                "blocked_total": rm.get("blocked_total", 0),
                "guardrails_blocked": rm.get("guardrails_blocked_total", 0),
                "data_security_blocked": rm.get("data_security_blocked_total", 0),
            }
        else:
            result["error"] = "Could not reach gateway"

        return json.dumps(result, indent=2)
