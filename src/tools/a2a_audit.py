"""
Tool: thinkneo_a2a_audit
Full audit trail of agent-to-agent interactions with filtering.
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
        name="thinkneo_a2a_audit",
        description=(
            "Full audit trail of agent-to-agent interactions. Shows every delegation, "
            "data request, escalation, and approval between agents with timestamps, costs, "
            "and outcomes. Supports filtering by agent, action, outcome, and time window. "
            "Essential for compliance, debugging, and understanding multi-agent behavior."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_a2a_audit(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        from_agent: Annotated[Optional[str], Field(description="Filter by source agent")] = None,
        to_agent: Annotated[Optional[str], Field(description="Filter by target agent")] = None,
        action: Annotated[Optional[str], Field(description="Filter by action type")] = None,
        outcome: Annotated[Optional[str], Field(description="Filter by outcome: 'success', 'error', 'timeout', 'rejected'")] = None,
        hours: Annotated[int, Field(description="Lookback window in hours")] = 24,
        limit: Annotated[int, Field(description="Maximum number of records")] = 50,
    ) -> str:
        """Full audit trail of agent-to-agent interactions. Shows every delegation, data request, escalation, and approval between agents with timestamps, costs, and outcomes. Supports filtering by agent, action, outcome, and time window."""
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        filters = [f"key_hash = '{key_h}'", f"workspace = '{workspace}'",
                    f"initiated_at >= now() - interval '{hours} hours'"]
        if from_agent:
            filters.append(f"from_agent = '{from_agent}'")
        if to_agent:
            filters.append(f"to_agent = '{to_agent}'")
        if action:
            filters.append(f"action = '{action}'")
        if outcome:
            filters.append(f"outcome = '{outcome}'")
        where = " AND ".join(filters)

        try:
            conn = _get_conn()

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT id, from_agent, to_agent, action, task_description,
                        cost_usd, outcome, latency_ms, error_message, metadata,
                        initiated_at::text, completed_at::text
                    FROM a2a_interactions
                    WHERE {where}  -- parameterized conditions (%s placeholders)
                    ORDER BY initiated_at DESC
                    LIMIT {min(limit, 200)}
                """)
                rows = cur.fetchall()

            # Summary stats
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE outcome = 'success') as successes,
                        COUNT(*) FILTER (WHERE outcome IN ('error', 'timeout')) as failures,
                        ROUND(SUM(cost_usd)::numeric, 4) as total_cost,
                        ROUND(AVG(latency_ms)::numeric, 0) as avg_latency,
                        COUNT(DISTINCT from_agent || '->' || to_agent) as unique_pairs
                    FROM a2a_interactions
                    WHERE {where}  -- parameterized conditions (%s placeholders)
                """)
                stats = cur.fetchone()

            # Active policies
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT from_agent, to_agent, allowed_actions, max_cost_per_call_usd,
                        max_calls_per_hour, require_approval, enabled
                    FROM a2a_policies
                    WHERE key_hash = %s AND workspace = %s
                    ORDER BY from_agent, to_agent
                """, (key_h, workspace))
                policies = [dict(r) for r in cur.fetchall()]
                for p in policies:
                    if p.get("max_cost_per_call_usd"):
                        p["max_cost_per_call_usd"] = float(p["max_cost_per_call_usd"])

            conn.close()

            interactions = []
            for r in rows:
                entry = {
                    "id": r["id"],
                    "from": r["from_agent"],
                    "to": r["to_agent"],
                    "action": r["action"],
                    "task": r["task_description"],
                    "cost_usd": float(r["cost_usd"] or 0),
                    "outcome": r["outcome"],
                    "latency_ms": r["latency_ms"],
                    "initiated_at": r["initiated_at"],
                }
                if r["error_message"]:
                    entry["error"] = r["error_message"]
                if r["metadata"] and r["metadata"] != {}:
                    entry["metadata"] = r["metadata"]
                interactions.append(entry)

            return json.dumps({
                "audit": {
                    "period_hours": hours,
                    "workspace": workspace,
                    "total_interactions": stats["total"],
                    "successes": stats["successes"],
                    "failures": stats["failures"],
                    "success_rate_pct": round(stats["successes"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0,
                    "total_cost_usd": float(stats["total_cost"] or 0),
                    "avg_latency_ms": int(stats["avg_latency"]) if stats["avg_latency"] else None,
                    "unique_agent_pairs": stats["unique_pairs"],
                },
                "interactions": interactions,
                "active_policies": policies,
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
