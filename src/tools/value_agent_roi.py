"""
Tool: thinkneo_agent_roi
Calculate ROI per AI agent: value generated vs AI cost, with trend analysis.
Requires authentication.
"""
from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ..database import hash_key, _get_conn
from ._common import utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_agent_roi",
        description=(
            "Calculate ROI per AI agent. Shows value generated vs AI cost consumed, "
            "with daily trend, success rate, and comparison to pre-AI baseline. "
            "Answers: 'Is this agent generating or consuming value?' and 'What's the ROI trend?'"
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_agent_roi(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        agent_name: Annotated[Optional[str], Field(description="Specific agent to analyze. If omitted, returns all agents.")] = None,
        days: Annotated[int, Field(description="Number of days to analyze")] = 30,
    ) -> str:
        """Calculate ROI per AI agent. Shows value generated vs AI cost consumed, with daily trend, success rate, and comparison to pre-AI baseline."""
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        try:
            conn = _get_conn()

            agent_filter = f"AND agent_name = '{agent_name}'" if agent_name else ""

            # Aggregate per agent
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        agent_name,
                        SUM(total_decisions) as decisions,
                        SUM(successful_decisions) as successful,
                        ROUND(SUM(total_ai_cost_usd)::numeric, 4) as total_cost,
                        ROUND(SUM(total_value_generated_usd)::numeric, 2) as total_value,
                        ROUND(SUM(total_risk_avoided_usd)::numeric, 2) as risk_avoided,
                        ROUND(AVG(avg_confidence)::numeric, 2) as confidence
                    FROM agent_value_daily
                    WHERE key_hash = %s AND workspace = %s
                      AND day >= CURRENT_DATE - interval '{days} days'
                      {agent_filter}
                    GROUP BY agent_name
                    ORDER BY total_value DESC
                """, (key_h, workspace))
                agents = cur.fetchall()

            # Daily trend for requested agent (or top agent)
            trend_agent = agent_name or (agents[0]["agent_name"] if agents else None)
            trend = []
            if trend_agent:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT day::text, total_decisions, total_ai_cost_usd, total_value_generated_usd, total_risk_avoided_usd
                        FROM agent_value_daily
                        WHERE key_hash = %s AND workspace = %s AND agent_name = %s
                          AND day >= CURRENT_DATE - interval '%s days'
                        ORDER BY day
                    """, (key_h, workspace, trend_agent, days))
                    trend = [
                        {
                            "date": r["day"],
                            "decisions": r["total_decisions"],
                            "ai_cost": float(r["total_ai_cost_usd"] or 0),
                            "value": float(r["total_value_generated_usd"] or 0),
                            "risk_avoided": float(r["total_risk_avoided_usd"] or 0),
                        }
                        for r in cur.fetchall()
                    ]

            conn.close()

            agent_results = []
            for a in agents:
                cost = float(a["total_cost"] or 0)
                value = float(a["total_value"] or 0)
                risk = float(a["risk_avoided"] or 0)
                total_impact = value + risk
                decisions = a["decisions"] or 0
                successful = a["successful"] or 0

                entry = {
                    "agent_name": a["agent_name"],
                    "period_days": days,
                    "total_decisions": decisions,
                    "success_rate_pct": round(successful / decisions * 100, 1) if decisions > 0 else 0,
                    "total_ai_cost_usd": cost,
                    "total_value_generated_usd": value,
                    "total_risk_avoided_usd": risk,
                    "total_business_impact_usd": round(total_impact, 2),
                    "roi": f"{round(total_impact / cost, 1)}:1" if cost > 0 else "infinite",
                    "avg_confidence": float(a["confidence"]) if a["confidence"] else None,
                    "verdict": "generating_value" if total_impact > cost else "consuming_value",
                }
                agent_results.append(entry)

            return json.dumps({
                "workspace": workspace,
                "period_days": days,
                "agents": agent_results,
                "daily_trend": trend,
                "trend_agent": trend_agent,
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
