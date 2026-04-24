"""
Tool: thinkneo_decision_cost
Analyze cost-per-decision for agents and processes. Shows what each AI decision actually costs
compared to the pre-AI baseline.
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
        name="thinkneo_decision_cost",
        description=(
            "Analyze cost-per-decision for AI agents. Shows the actual AI cost for each decision, "
            "compared to the pre-AI baseline. Answers: 'How much does each AI decision cost?' "
            "and 'How does it compare to doing it without AI?'"
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_decision_cost(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        agent_name: Annotated[Optional[str], Field(description="Filter by specific agent")] = None,
        process_name: Annotated[Optional[str], Field(description="Filter by specific process")] = None,
        period: Annotated[str, Field(description="Time period: 'today', 'this-week', 'this-month', 'all'")] = "this-month",
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        period_sql = {
            "today": "AND d.decided_at >= CURRENT_DATE",
            "this-week": "AND d.decided_at >= date_trunc('week', CURRENT_DATE)",
            "this-month": "AND d.decided_at >= date_trunc('month', CURRENT_DATE)",
            "all": "",
        }.get(period, "AND d.decided_at >= date_trunc('month', CURRENT_DATE)")

        filters = [f"d.key_hash = '{key_h}'", f"d.workspace = '{workspace}'"]
        if agent_name:
            filters.append(f"d.agent_name = '{agent_name}'")
        if process_name:
            filters.append(f"d.process_name = '{process_name}'")
        where = " AND ".join(filters)

        try:
            conn = _get_conn()

            # Per-agent breakdown
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        d.agent_name,
                        d.process_name,
                        COUNT(*) as total_decisions,
                        COUNT(*) FILTER (WHERE d.outcome = 'success') as successful,
                        ROUND(AVG(d.ai_cost_usd)::numeric, 6) as avg_cost_per_decision,
                        ROUND(SUM(d.ai_cost_usd)::numeric, 4) as total_ai_cost,
                        ROUND(SUM(COALESCE(d.value_generated_usd, 0))::numeric, 2) as total_value,
                        ROUND(AVG(d.confidence)::numeric, 2) as avg_confidence
                    FROM decisions d
                    WHERE {where} {period_sql}
                    GROUP BY d.agent_name, d.process_name
                    ORDER BY total_decisions DESC
                    LIMIT 20
                """)
                agents = cur.fetchall()

            # Get baselines for comparison
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT process_name, cost_per_unit_usd, unit_label FROM value_baselines WHERE key_hash=%s AND workspace=%s",
                    (key_h, workspace)
                )
                baselines_raw = cur.fetchall()
            baselines = {b["process_name"]: b for b in baselines_raw}

            conn.close()

            breakdown = []
            total_cost = 0.0
            total_value = 0.0
            total_decisions = 0

            for a in agents:
                avg_cost = float(a["avg_cost_per_decision"] or 0)
                t_cost = float(a["total_ai_cost"] or 0)
                t_value = float(a["total_value"] or 0)
                count = a["total_decisions"]

                entry = {
                    "agent": a["agent_name"],
                    "process": a["process_name"],
                    "decisions": count,
                    "successful": a["successful"],
                    "avg_cost_per_decision_usd": avg_cost,
                    "total_ai_cost_usd": t_cost,
                    "total_value_generated_usd": t_value,
                    "avg_confidence": float(a["avg_confidence"]) if a["avg_confidence"] else None,
                }

                bl = baselines.get(a["process_name"])
                if bl:
                    human_cost = float(bl["cost_per_unit_usd"])
                    entry["baseline_cost_per_unit_usd"] = human_cost
                    entry["cost_reduction_pct"] = round((1 - avg_cost / human_cost) * 100, 1) if human_cost > 0 else None
                    entry["savings_per_decision_usd"] = round(human_cost - avg_cost, 4)

                if t_cost > 0 and t_value > 0:
                    entry["roi"] = f"{round(t_value / t_cost, 1)}:1"

                breakdown.append(entry)
                total_cost += t_cost
                total_value += t_value
                total_decisions += count

            return json.dumps({
                "period": period,
                "workspace": workspace,
                "total_decisions": total_decisions,
                "total_ai_cost_usd": round(total_cost, 4),
                "total_value_generated_usd": round(total_value, 2),
                "overall_roi": f"{round(total_value / total_cost, 1)}:1" if total_cost > 0 and total_value > 0 else None,
                "avg_cost_per_decision_usd": round(total_cost / total_decisions, 6) if total_decisions > 0 else 0,
                "breakdown": breakdown,
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
