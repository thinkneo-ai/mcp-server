"""
Tools: Agent SLA — Outcome Service Level Agreements

4 MCP tools:
  - thinkneo_sla_define: Define/update an SLA for an agent
  - thinkneo_sla_status: Check current SLA status
  - thinkneo_sla_breaches: View breach history
  - thinkneo_sla_dashboard: Overview dashboard
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ..agent_sla import define_sla, get_sla_status, get_breaches, get_sla_dashboard
from .._common_obs import utcnow_obs


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="thinkneo_sla_define",
        description=(
            "Define or update an SLA (Service Level Agreement) for an AI agent. "
            "Set accuracy, quality, cost, safety, or latency thresholds with automatic "
            "breach detection and configurable actions (alert, escalate, disable, switch_model). "
            "Like SRE SLOs but for AI agent outcomes. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_sla_define(
        agent_name: Annotated[str, Field(description="Agent name to set SLA for (e.g., 'support-bot', 'finance-agent')")],
        metric: Annotated[str, Field(
            description="Metric to monitor: 'accuracy' (outcome verification rate %), 'response_quality' (avg quality score), 'cost_efficiency' (cost per verified outcome), 'safety' (guardrail pass rate %), 'latency' (avg response ms)"
        )],
        threshold: Annotated[float, Field(description="Target threshold value (e.g., 95.0 for 95% accuracy)")],
        window: Annotated[str, Field(description="Rolling window: '1h', '24h', '7d', or '30d'")] = "7d",
        breach_action: Annotated[str, Field(
            description="Action on breach: 'alert' (notify), 'escalate' (notify + flag), 'disable' (stop agent), 'switch_model' (fallback model)"
        )] = "alert",
        threshold_direction: Annotated[str, Field(
            description="'min' = actual must be >= threshold (for accuracy, quality). 'max' = actual must be <= threshold (for cost, latency)."
        )] = "min",
    ) -> str:
        token = require_auth()

        result = define_sla(
            api_key=token, agent_name=agent_name, metric=metric,
            threshold=threshold, window=window, breach_action=breach_action,
            threshold_direction=threshold_direction,
        )
        result["generated_at"] = utcnow_obs()
        result["_hint"] = "SLA defined. Use thinkneo_sla_status to check current status."
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_sla_status",
        description=(
            "Check current SLA status for all agents or a specific agent. Shows actual "
            "metric values vs thresholds, healthy/breached status, and error budget remaining. "
            "Automatically records breaches. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_sla_status(
        agent_name: Annotated[Optional[str], Field(
            description="Optional: specific agent name. Leave empty for all agents."
        )] = None,
    ) -> str:
        token = require_auth()

        result = get_sla_status(api_key=token, agent_name=agent_name)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_sla_breaches",
        description=(
            "View SLA breach history — which SLAs were breached, by which agents, "
            "actual vs threshold values, and resolution status. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_sla_breaches(
        days: Annotated[int, Field(description="Days to look back (default 30)")] = 30,
        agent_name: Annotated[Optional[str], Field(description="Filter by agent name")] = None,
    ) -> str:
        token = require_auth()

        result = get_breaches(api_key=token, days=min(max(days, 1), 365), agent_name=agent_name)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_sla_dashboard",
        description=(
            "SLA overview dashboard — all agents, current status, error budgets, "
            "and recent breaches (7d). The SRE dashboard for AI agents. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_sla_dashboard() -> str:
        token = require_auth()

        result = get_sla_dashboard(api_key=token)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)
