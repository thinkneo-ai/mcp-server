"""
Tool: thinkneo_a2a_set_policy
Define policies for agent-to-agent communication — who can talk to whom and do what.
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
        name="thinkneo_a2a_set_policy",
        description=(
            "Define a policy for agent-to-agent communication. Controls which agents can talk to each other, "
            "what actions are allowed, cost limits per call, and rate limits. "
            "Example: 'support-bot can delegate_task to billing-agent, max $0.10/call, max 100 calls/hour'."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_a2a_set_policy(
        from_agent: Annotated[str, Field(description="Source agent name (or '*' for any agent)")],
        to_agent: Annotated[str, Field(description="Target agent name (or '*' for any agent)")],
        allowed_actions: Annotated[Optional[str], Field(description="Comma-separated actions: 'delegate_task,request_data,escalate' or '*' for all")] = "*",
        max_cost_per_call_usd: Annotated[Optional[float], Field(description="Maximum cost per interaction in USD")] = None,
        max_calls_per_hour: Annotated[Optional[int], Field(description="Maximum calls per hour for this pair")] = None,
        require_approval: Annotated[bool, Field(description="Require human approval before execution")] = False,
        enabled: Annotated[bool, Field(description="Enable or disable this policy")] = True,
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        actions = [a.strip() for a in (allowed_actions or "*").split(",") if a.strip()]

        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO a2a_policies (key_hash, workspace, from_agent, to_agent,
                        allowed_actions, max_cost_per_call_usd, max_calls_per_hour, require_approval, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (key_hash, workspace, from_agent, to_agent)
                    DO UPDATE SET
                        allowed_actions = EXCLUDED.allowed_actions,
                        max_cost_per_call_usd = EXCLUDED.max_cost_per_call_usd,
                        max_calls_per_hour = EXCLUDED.max_calls_per_hour,
                        require_approval = EXCLUDED.require_approval,
                        enabled = EXCLUDED.enabled
                    RETURNING id, created_at
                """, (key_h, workspace, from_agent, to_agent,
                      actions, max_cost_per_call_usd, max_calls_per_hour, require_approval, enabled))
                row = cur.fetchone()
            conn.close()

            return json.dumps({
                "status": "policy_set",
                "policy_id": row["id"],
                "from_agent": from_agent,
                "to_agent": to_agent,
                "allowed_actions": actions,
                "max_cost_per_call_usd": max_cost_per_call_usd,
                "max_calls_per_hour": max_calls_per_hour,
                "require_approval": require_approval,
                "enabled": enabled,
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
