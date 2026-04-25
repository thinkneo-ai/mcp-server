"""
Tool: thinkneo_a2a_log
Log an agent-to-agent interaction with cost, outcome, and latency.
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
        name="thinkneo_a2a_log",
        description=(
            "Log an agent-to-agent interaction. Tracks which agent called which, "
            "what action was performed, the cost, outcome, and latency. "
            "Also enforces A2A policies if configured — returns policy_blocked if the interaction is not allowed."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_a2a_log(
        from_agent: Annotated[str, Field(description="Name of the calling agent, e.g. 'orchestrator', 'support-bot'")],
        to_agent: Annotated[str, Field(description="Name of the target agent, e.g. 'billing-agent', 'knowledge-retriever'")],
        action: Annotated[str, Field(description="Action performed: 'delegate_task', 'request_data', 'escalate', 'approve', 'notify'")],
        task_description: Annotated[Optional[str], Field(description="What was delegated or requested")] = None,
        cost_usd: Annotated[float, Field(description="Cost of this interaction in USD")] = 0.0,
        outcome: Annotated[str, Field(description="Result: 'success', 'error', 'timeout', 'rejected', 'pending'")] = "success",
        latency_ms: Annotated[Optional[int], Field(description="Latency in milliseconds")] = None,
        error_message: Annotated[Optional[str], Field(description="Error message if outcome is 'error'")] = None,
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        metadata: Annotated[Optional[str], Field(description="JSON string with additional context")] = None,
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        meta = {}
        if metadata:
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError:
                meta = {"raw": metadata}

        try:
            conn = _get_conn()

            # Check A2A policy
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT allowed_actions, max_cost_per_call_usd, max_calls_per_hour, require_approval, enabled
                    FROM a2a_policies
                    WHERE key_hash = %s AND workspace = %s AND from_agent = %s AND to_agent = %s
                """, (key_h, workspace, from_agent, to_agent))
                policy = cur.fetchone()

            if policy:
                if not policy["enabled"]:
                    conn.close()
                    return json.dumps({
                        "status": "policy_blocked",
                        "reason": "interaction_disabled",
                        "from_agent": from_agent,
                        "to_agent": to_agent,
                        "message": f"A2A policy blocks {from_agent} -> {to_agent}: interaction disabled",
                        "generated_at": utcnow(),
                    }, indent=2)

                allowed = policy["allowed_actions"]
                if allowed and "*" not in allowed and action not in allowed:
                    conn.close()
                    return json.dumps({
                        "status": "policy_blocked",
                        "reason": "action_not_allowed",
                        "from_agent": from_agent,
                        "to_agent": to_agent,
                        "action": action,
                        "allowed_actions": allowed,
                        "message": f"Action '{action}' not in allowed list for {from_agent} -> {to_agent}",
                        "generated_at": utcnow(),
                    }, indent=2)

                max_cost = policy["max_cost_per_call_usd"]
                if max_cost and cost_usd > float(max_cost):
                    conn.close()
                    return json.dumps({
                        "status": "policy_blocked",
                        "reason": "cost_exceeds_limit",
                        "cost_usd": cost_usd,
                        "max_cost_usd": float(max_cost),
                        "message": f"Cost ${cost_usd:.4f} exceeds policy limit ${float(max_cost):.4f}",
                        "generated_at": utcnow(),
                    }, indent=2)

                max_calls = policy["max_calls_per_hour"]
                if max_calls:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT COUNT(*) as cnt FROM a2a_interactions
                            WHERE key_hash = %s AND workspace = %s AND from_agent = %s AND to_agent = %s
                              AND initiated_at >= now() - interval '1 hour'
                        """, (key_h, workspace, from_agent, to_agent))
                        cnt = cur.fetchone()["cnt"]
                    if cnt >= max_calls:
                        conn.close()
                        return json.dumps({
                            "status": "policy_blocked",
                            "reason": "rate_limit_exceeded",
                            "calls_this_hour": cnt,
                            "max_calls_per_hour": max_calls,
                            "message": f"{from_agent} -> {to_agent}: {cnt}/{max_calls} calls/hour exceeded",
                            "generated_at": utcnow(),
                        }, indent=2)

            # Log the interaction
            completed = utcnow() if outcome != "pending" else None
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO a2a_interactions (key_hash, workspace, from_agent, to_agent, action,
                        task_description, cost_usd, outcome, latency_ms, error_message, metadata, completed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, initiated_at
                """, (key_h, workspace, from_agent, to_agent, action,
                      task_description, cost_usd, outcome, latency_ms, error_message,
                      json.dumps(meta), completed))
                row = cur.fetchone()

            # Update hourly aggregate
            hour_bucket = row["initiated_at"].strftime("%Y-%m-%d %H:00:00+00")
            is_success = 1 if outcome == "success" else 0
            is_error = 1 if outcome in ("error", "timeout") else 0
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO a2a_flow_hourly (key_hash, workspace, from_agent, to_agent, hour,
                        call_count, success_count, error_count, total_cost_usd, avg_latency_ms)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s)
                    ON CONFLICT (key_hash, workspace, from_agent, to_agent, hour)
                    DO UPDATE SET
                        call_count = a2a_flow_hourly.call_count + 1,
                        success_count = a2a_flow_hourly.success_count + EXCLUDED.success_count,
                        error_count = a2a_flow_hourly.error_count + EXCLUDED.error_count,
                        total_cost_usd = a2a_flow_hourly.total_cost_usd + EXCLUDED.total_cost_usd,
                        avg_latency_ms = (COALESCE(a2a_flow_hourly.avg_latency_ms, 0) * a2a_flow_hourly.call_count
                                          + COALESCE(EXCLUDED.avg_latency_ms, 0))
                                         / (a2a_flow_hourly.call_count + 1)
                """, (key_h, workspace, from_agent, to_agent, hour_bucket,
                      is_success, is_error, cost_usd, latency_ms))

            conn.close()

            return json.dumps({
                "status": "interaction_logged",
                "interaction_id": row["id"],
                "from_agent": from_agent,
                "to_agent": to_agent,
                "action": action,
                "cost_usd": cost_usd,
                "outcome": outcome,
                "policy_applied": policy is not None,
                "initiated_at": row["initiated_at"].isoformat(),
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
