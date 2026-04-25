"""
Tool: thinkneo_log_decision
Log a business decision made by an AI agent, with cost and value attribution.
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
        name="thinkneo_log_decision",
        description=(
            "Log a business decision made by an AI agent. Tracks the AI cost and the business value generated. "
            "If a baseline exists for the process, value is auto-calculated from the baseline cost. "
            "Example: agent 'support-bot' resolved a 'customer_support_ticket' at $0.03 AI cost, "
            "replacing a $12 human-handled ticket. ROI: 400:1."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_log_decision(
        agent_name: Annotated[str, Field(description="Name of the AI agent that made the decision, e.g. 'support-bot', 'loan-reviewer'")],
        decision_type: Annotated[str, Field(description="Type of decision, e.g. 'ticket_resolved', 'loan_approved', 'content_reviewed'")],
        ai_cost_usd: Annotated[float, Field(description="Actual AI cost for this decision in USD, e.g. 0.03")] = 0.0,
        process_name: Annotated[Optional[str], Field(description="Links to a baseline process for auto ROI calculation")] = None,
        value_generated_usd: Annotated[Optional[float], Field(description="Explicit business value in USD. If omitted and process_name has a baseline, auto-calculated.")] = None,
        outcome: Annotated[str, Field(description="Result: 'success', 'escalated', 'rejected', 'error'")] = "success",
        confidence: Annotated[Optional[float], Field(description="Confidence score 0.0-1.0")] = None,
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

            # Auto-calculate value from baseline if not provided
            actual_value = value_generated_usd
            baseline_used = None
            if actual_value is None and process_name:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT cost_per_unit_usd, unit_label FROM value_baselines WHERE key_hash=%s AND workspace=%s AND process_name=%s",
                        (key_h, workspace, process_name)
                    )
                    bl = cur.fetchone()
                    if bl:
                        actual_value = float(bl["cost_per_unit_usd"])
                        baseline_used = f"${bl['cost_per_unit_usd']:.2f} per {bl['unit_label']}"

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO decisions (key_hash, workspace, agent_name, decision_type, process_name,
                        ai_cost_usd, value_generated_usd, outcome, confidence, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, decided_at
                """, (key_h, workspace, agent_name, decision_type, process_name,
                      ai_cost_usd, actual_value, outcome, confidence, json.dumps(meta)))
                row = cur.fetchone()

            # Update daily aggregate
            day_str = row["decided_at"].strftime("%Y-%m-%d")
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO agent_value_daily (key_hash, workspace, agent_name, day,
                        total_decisions, successful_decisions, total_ai_cost_usd, total_value_generated_usd, avg_confidence)
                    VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
                    ON CONFLICT (key_hash, workspace, agent_name, day)
                    DO UPDATE SET
                        total_decisions = agent_value_daily.total_decisions + 1,
                        successful_decisions = agent_value_daily.successful_decisions + EXCLUDED.successful_decisions,
                        total_ai_cost_usd = agent_value_daily.total_ai_cost_usd + EXCLUDED.total_ai_cost_usd,
                        total_value_generated_usd = agent_value_daily.total_value_generated_usd + EXCLUDED.total_value_generated_usd,
                        avg_confidence = (agent_value_daily.avg_confidence * agent_value_daily.total_decisions + COALESCE(EXCLUDED.avg_confidence, 0))
                                         / (agent_value_daily.total_decisions + 1)
                """, (key_h, workspace, agent_name, day_str,
                      1 if outcome == "success" else 0,
                      ai_cost_usd, actual_value or 0, confidence))

            conn.close()

            roi = None
            if actual_value and ai_cost_usd and ai_cost_usd > 0:
                roi = round(actual_value / ai_cost_usd, 1)

            return json.dumps({
                "status": "decision_logged",
                "decision_id": row["id"],
                "agent_name": agent_name,
                "decision_type": decision_type,
                "ai_cost_usd": ai_cost_usd,
                "value_generated_usd": actual_value,
                "baseline_used": baseline_used,
                "roi": f"{roi}:1" if roi else None,
                "outcome": outcome,
                "decided_at": row["decided_at"].isoformat(),
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
