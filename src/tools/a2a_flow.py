"""
Tool: thinkneo_a2a_flow_map
Visualize agent-to-agent communication patterns — who talks to whom, how often, cost, errors.
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
        name="thinkneo_a2a_flow_map",
        description=(
            "Map agent-to-agent communication flows. Shows which agents talk to each other, "
            "call frequency, cost, error rates, and latency. Identifies hot paths, bottlenecks, "
            "and anomalous patterns like agent loops or unexpected delegations."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_a2a_flow_map(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        hours: Annotated[int, Field(description="Lookback window in hours")] = 24,
        agent_name: Annotated[Optional[str], Field(description="Filter flows involving this agent (as source or target)")] = None,
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        agent_filter = ""
        agent_filter_params = []
        if agent_name:
            agent_filter = "AND (from_agent = %s OR to_agent = %s)"
            agent_filter_params = [agent_name, agent_name]

        try:
            conn = _get_conn()

            # Get flow edges
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT from_agent, to_agent,
                        SUM(call_count) as calls,
                        SUM(success_count) as successes,
                        SUM(error_count) as errors,
                        ROUND(SUM(total_cost_usd)::numeric, 4) as cost,
                        ROUND(AVG(avg_latency_ms)::numeric, 0) as latency
                    FROM a2a_flow_hourly
                    WHERE key_hash = %s AND workspace = %s
                      AND hour >= now() - make_interval(hours => %s)
                      {agent_filter}
                    GROUP BY from_agent, to_agent
                    ORDER BY calls DESC
                    LIMIT 50
                """, (key_h, workspace))
                edges = cur.fetchall()

            # Get unique agents and their stats
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT agent, SUM(out_calls) as outgoing, SUM(in_calls) as incoming, SUM(cost) as total_cost
                    FROM (
                        SELECT from_agent as agent, SUM(call_count) as out_calls, 0 as in_calls, SUM(total_cost_usd) as cost
                        FROM a2a_flow_hourly
                        WHERE key_hash = %s AND workspace = %s AND hour >= now() - make_interval(hours => %s)
                        GROUP BY from_agent
                        UNION ALL
                        SELECT to_agent as agent, 0 as out_calls, SUM(call_count) as in_calls, 0 as cost
                        FROM a2a_flow_hourly
                        WHERE key_hash = %s AND workspace = %s AND hour >= now() - make_interval(hours => %s)
                        GROUP BY to_agent
                    ) combined
                    GROUP BY agent
                    ORDER BY outgoing + incoming DESC
                """, (key_h, workspace, key_h, workspace))
                nodes = cur.fetchall()

            # Detect anomalies
            with conn.cursor() as cur:
                # Check for loops (A->B->A)
                cur.execute(f"""
                    SELECT a.from_agent, a.to_agent, SUM(a.call_count) as forward, SUM(b.call_count) as reverse
                    FROM a2a_flow_hourly a
                    JOIN a2a_flow_hourly b ON a.key_hash = b.key_hash AND a.workspace = b.workspace
                        AND a.from_agent = b.to_agent AND a.to_agent = b.from_agent
                        AND b.hour >= now() - make_interval(hours => %s)
                    WHERE a.key_hash = %s AND a.workspace = %s
                      AND a.hour >= now() - make_interval(hours => %s)
                    GROUP BY a.from_agent, a.to_agent
                    HAVING SUM(b.call_count) > 0
                """, (key_h, workspace))
                loops = [
                    {
                        "agents": [r["from_agent"], r["to_agent"]],
                        "forward_calls": r["forward"],
                        "reverse_calls": r["reverse"],
                        "warning": "bidirectional_communication" if r["reverse"] < r["forward"] * 0.5 else "potential_loop",
                    }
                    for r in cur.fetchall()
                ]

            # Recent errors
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT from_agent, to_agent, action, error_message, initiated_at::text
                    FROM a2a_interactions
                    WHERE key_hash = %s AND workspace = %s
                      AND outcome IN ('error', 'timeout')
                      AND initiated_at >= now() - make_interval(hours => %s)
                    ORDER BY initiated_at DESC
                    LIMIT 10
                """, (key_h, workspace))
                recent_errors = [dict(r) for r in cur.fetchall()]

            conn.close()

            flow_edges = [
                {
                    "from": e["from_agent"],
                    "to": e["to_agent"],
                    "calls": e["calls"],
                    "success_rate_pct": round(e["successes"] / e["calls"] * 100, 1) if e["calls"] > 0 else 0,
                    "error_count": e["errors"],
                    "cost_usd": float(e["cost"] or 0),
                    "avg_latency_ms": int(e["latency"]) if e["latency"] else None,
                }
                for e in edges
            ]

            agent_nodes = [
                {
                    "agent": n["agent"],
                    "outgoing_calls": n["outgoing"],
                    "incoming_calls": n["incoming"],
                    "role": "orchestrator" if n["outgoing"] > n["incoming"] * 2 else
                            "worker" if n["incoming"] > n["outgoing"] * 2 else "peer",
                    "total_cost_usd": float(n["total_cost"] or 0),
                }
                for n in nodes
            ]

            total_calls = sum(e["calls"] for e in flow_edges)
            total_cost = sum(e["cost_usd"] for e in flow_edges)
            total_errors = sum(e["error_count"] for e in flow_edges)

            return json.dumps({
                "flow_map": {
                    "period_hours": hours,
                    "workspace": workspace,
                    "total_interactions": total_calls,
                    "total_cost_usd": round(total_cost, 4),
                    "total_errors": total_errors,
                    "error_rate_pct": round(total_errors / total_calls * 100, 1) if total_calls > 0 else 0,
                    "unique_agents": len(agent_nodes),
                    "unique_edges": len(flow_edges),
                },
                "agents": agent_nodes,
                "edges": flow_edges,
                "anomalies": loops,
                "recent_errors": recent_errors,
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
