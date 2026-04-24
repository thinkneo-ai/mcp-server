"""
Tool: thinkneo_detect_waste
Analyze AI operations to find waste, inefficiency, and optimization opportunities.
Returns specific dollar amounts: "you're losing $X/month here", "this flow is 5x more expensive than it should be".
Requires authentication.
"""
from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ..database import hash_key, _get_conn
from ._common import utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_detect_waste",
        description=(
            "Detect waste and inefficiency in AI operations. Analyzes agent performance, "
            "A2A communication overhead, error costs, unused capacity, and cost outliers. "
            "Returns specific actionable findings like 'you are losing $3,200/month on error retries' "
            "or 'this flow is 5x more expensive than your best-performing flow'. "
            "This is the diagnostic tool that creates the buying trigger."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_detect_waste(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        days: Annotated[int, Field(description="Analysis window in days")] = 30,
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        findings = []

        try:
            conn = _get_conn()

            # 1. Error cost analysis — money burned on failed decisions
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        agent_name,
                        COUNT(*) FILTER (WHERE outcome != 'success') as errors,
                        COUNT(*) as total,
                        ROUND(SUM(CASE WHEN outcome != 'success' THEN ai_cost_usd ELSE 0 END)::numeric, 4) as error_cost,
                        ROUND(SUM(ai_cost_usd)::numeric, 4) as total_cost
                    FROM decisions
                    WHERE key_hash = %s AND workspace = %s
                      AND decided_at >= CURRENT_DATE - interval '%s days'
                    GROUP BY agent_name
                    HAVING COUNT(*) FILTER (WHERE outcome != 'success') > 0
                    ORDER BY error_cost DESC
                """, (key_h, workspace, days))
                for r in cur.fetchall():
                    error_pct = round(r["errors"] / r["total"] * 100, 1)
                    monthly_error_cost = float(r["error_cost"]) * (30 / max(days, 1))
                    if monthly_error_cost > 0:
                        findings.append({
                            "type": "error_waste",
                            "severity": "high" if error_pct > 20 else "medium",
                            "agent": r["agent_name"],
                            "finding": f"Agent '{r['agent_name']}' has {error_pct}% error rate — burning ${monthly_error_cost:.2f}/month on failed decisions",
                            "monthly_waste_usd": round(monthly_error_cost, 2),
                            "errors": r["errors"],
                            "total_decisions": r["total"],
                            "fix": "Review error patterns, add guardrails, or retrain the agent",
                        })

            # 2. Overpriced agents — compare cost per decision across agents doing the same process
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT process_name, agent_name,
                        ROUND(AVG(ai_cost_usd)::numeric, 6) as avg_cost,
                        COUNT(*) as decisions
                    FROM decisions
                    WHERE key_hash = %s AND workspace = %s AND process_name IS NOT NULL
                      AND decided_at >= CURRENT_DATE - interval '%s days'
                    GROUP BY process_name, agent_name
                    HAVING COUNT(*) >= 3
                    ORDER BY process_name, avg_cost
                """, (key_h, workspace, days))
                by_process = {}
                for r in cur.fetchall():
                    p = r["process_name"]
                    if p not in by_process:
                        by_process[p] = []
                    by_process[p].append(r)

                for process, agents in by_process.items():
                    if len(agents) < 2:
                        continue
                    cheapest = float(agents[0]["avg_cost"])
                    for a in agents[1:]:
                        cost = float(a["avg_cost"])
                        if cheapest > 0 and cost / cheapest > 2:
                            ratio = round(cost / cheapest, 1)
                            monthly_excess = (cost - cheapest) * a["decisions"] * (30 / max(days, 1))
                            findings.append({
                                "type": "cost_outlier",
                                "severity": "high" if ratio > 5 else "medium",
                                "agent": a["agent_name"],
                                "process": process,
                                "finding": f"'{a['agent_name']}' costs {ratio}x more than '{agents[0]['agent_name']}' for '{process}' — ${cost:.4f} vs ${cheapest:.4f}/decision",
                                "monthly_waste_usd": round(monthly_excess, 2),
                                "fix": f"Route '{process}' tasks to '{agents[0]['agent_name']}' or optimize '{a['agent_name']}'",
                            })

            # 3. A2A communication overhead — expensive or error-prone agent pairs
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT from_agent, to_agent,
                        SUM(call_count) as calls,
                        SUM(error_count) as errors,
                        ROUND(SUM(total_cost_usd)::numeric, 4) as cost
                    FROM a2a_flow_hourly
                    WHERE key_hash = %s AND workspace = %s
                      AND hour >= CURRENT_DATE - interval '%s days'
                    GROUP BY from_agent, to_agent
                    HAVING SUM(error_count) > 0 OR SUM(total_cost_usd) > 0.10
                    ORDER BY cost DESC
                """, (key_h, workspace, days))
                for r in cur.fetchall():
                    calls = r["calls"]
                    errors = r["errors"]
                    cost = float(r["cost"] or 0)
                    if errors > 0 and calls > 0:
                        error_pct = round(errors / calls * 100, 1)
                        if error_pct > 10:
                            monthly_waste = cost * (errors / calls) * (30 / max(days, 1))
                            findings.append({
                                "type": "a2a_error_overhead",
                                "severity": "high" if error_pct > 30 else "medium",
                                "from_agent": r["from_agent"],
                                "to_agent": r["to_agent"],
                                "finding": f"A2A {r['from_agent']} -> {r['to_agent']}: {error_pct}% error rate ({errors}/{calls} calls) — ${monthly_waste:.2f}/month wasted on failed handoffs",
                                "monthly_waste_usd": round(monthly_waste, 2),
                                "fix": "Add retry policies, circuit breakers, or fix the receiving agent",
                            })

            # 4. Underperforming agents — low ROI compared to baseline
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT d.agent_name,
                        COUNT(*) as decisions,
                        ROUND(SUM(d.ai_cost_usd)::numeric, 4) as total_cost,
                        ROUND(SUM(COALESCE(d.value_generated_usd, 0))::numeric, 2) as total_value
                    FROM decisions d
                    WHERE d.key_hash = %s AND d.workspace = %s
                      AND d.decided_at >= CURRENT_DATE - interval '%s days'
                    GROUP BY d.agent_name
                    HAVING SUM(d.ai_cost_usd) > 0
                    ORDER BY total_cost DESC
                """, (key_h, workspace, days))
                for r in cur.fetchall():
                    cost = float(r["total_cost"] or 0)
                    value = float(r["total_value"] or 0)
                    if cost > 0 and value > 0 and value / cost < 5:
                        monthly_gap = (cost * 5 - value) * (30 / max(days, 1))
                        findings.append({
                            "type": "low_roi_agent",
                            "severity": "medium",
                            "agent": r["agent_name"],
                            "finding": f"'{r['agent_name']}' ROI is only {round(value/cost, 1)}:1 — expected 5:1+ for an AI agent. Missing ${monthly_gap:.2f}/month in unrealized value",
                            "current_roi": f"{round(value/cost, 1)}:1",
                            "target_roi": "5:1",
                            "monthly_waste_usd": round(monthly_gap, 2),
                            "fix": "Optimize prompts, switch models, or reassign to higher-value tasks",
                        })

            # 5. Model cost optimization — compare to smart router suggestions
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) as total,
                        ROUND(SUM(cost_estimate_usd)::numeric, 4) as total_spent
                    FROM usage_log
                    WHERE key_hash = %s
                      AND called_at >= CURRENT_DATE - interval '%s days'
                """, (key_h, days))
                usage = cur.fetchone()

            if usage and float(usage["total_spent"] or 0) > 0:
                # Estimate potential savings from smart routing (typically 30-60%)
                total_spent = float(usage["total_spent"])
                estimated_savings = total_spent * 0.40  # conservative 40% savings
                monthly_savings = estimated_savings * (30 / max(days, 1))
                if monthly_savings > 1.0:
                    findings.append({
                        "type": "model_optimization",
                        "severity": "medium",
                        "finding": f"You spent ${total_spent:.2f} on API calls in {days} days. Smart routing could save ~40% = ${monthly_savings:.2f}/month",
                        "monthly_waste_usd": round(monthly_savings, 2),
                        "fix": "Enable thinkneo_route_model to auto-select cheapest model meeting quality threshold",
                    })

            conn.close()

            # Sort by monthly waste
            findings.sort(key=lambda f: f.get("monthly_waste_usd", 0), reverse=True)
            total_monthly_waste = sum(f.get("monthly_waste_usd", 0) for f in findings)
            annual_waste = total_monthly_waste * 12

            return json.dumps({
                "waste_report": "ThinkNEO AI Waste Detection",
                "period_days": days,
                "workspace": workspace,
                "headline": f"${total_monthly_waste:,.2f}/month in detectable waste ({len(findings)} findings)" if findings else "No significant waste detected",
                "annual_projection": f"${annual_waste:,.2f}/year at current rates" if annual_waste > 0 else None,
                "total_monthly_waste_usd": round(total_monthly_waste, 2),
                "findings_count": len(findings),
                "findings": findings,
                "recommendation": "Address high-severity findings first for immediate ROI improvement" if findings else "Operations are running efficiently",
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
