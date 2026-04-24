"""
Tool: thinkneo_log_risk_avoidance
Log a risk event that was blocked or avoided, with estimated dollar impact.
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

SEVERITY_MULTIPLIERS = {
    "low": 1.0,
    "medium": 5.0,
    "high": 25.0,
    "critical": 100.0,
}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_log_risk_avoidance",
        description=(
            "Log a risk event that was blocked or avoided by the governance layer. "
            "Quantifies the estimated dollar impact of the avoided risk. "
            "Examples: PII leak blocked (est. $50K GDPR fine), prompt injection prevented, "
            "policy violation caught before production. "
            "If estimated_impact_usd is not provided, a default is calculated from severity."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_log_risk_avoidance(
        risk_type: Annotated[str, Field(description="Type: 'pii_leak', 'injection_blocked', 'policy_violation', 'spend_limit', 'compliance_breach', 'data_exfiltration'")],
        severity: Annotated[str, Field(description="Severity level: 'low', 'medium', 'high', 'critical'")] = "medium",
        estimated_impact_usd: Annotated[Optional[float], Field(description="Estimated cost if this risk had materialized in USD")] = None,
        agent_name: Annotated[Optional[str], Field(description="Agent involved, if applicable")] = None,
        description: Annotated[Optional[str], Field(description="Brief description of what was blocked")] = None,
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        # Auto-estimate impact from severity if not provided
        impact = estimated_impact_usd
        auto_estimated = False
        if impact is None:
            multiplier = SEVERITY_MULTIPLIERS.get(severity, 5.0)
            base_costs = {
                "pii_leak": 5000.0,
                "injection_blocked": 1000.0,
                "policy_violation": 2500.0,
                "spend_limit": 500.0,
                "compliance_breach": 10000.0,
                "data_exfiltration": 25000.0,
            }
            base = base_costs.get(risk_type, 1000.0)
            impact = base * (multiplier / 5.0)
            auto_estimated = True

        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO risk_events (key_hash, workspace, agent_name, risk_type, severity, estimated_impact_usd, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, blocked_at
                """, (key_h, workspace, agent_name, risk_type, severity, impact, description))
                row = cur.fetchone()

            # Update daily aggregate for agent if specified
            if agent_name:
                day_str = row["blocked_at"].strftime("%Y-%m-%d")
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO agent_value_daily (key_hash, workspace, agent_name, day, total_risk_avoided_usd)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (key_hash, workspace, agent_name, day)
                        DO UPDATE SET total_risk_avoided_usd = agent_value_daily.total_risk_avoided_usd + EXCLUDED.total_risk_avoided_usd
                    """, (key_h, workspace, agent_name, day_str, impact))

            conn.close()

            return json.dumps({
                "status": "risk_logged",
                "event_id": row["id"],
                "risk_type": risk_type,
                "severity": severity,
                "estimated_impact_usd": impact,
                "auto_estimated": auto_estimated,
                "agent_name": agent_name,
                "blocked_at": row["blocked_at"].isoformat(),
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
