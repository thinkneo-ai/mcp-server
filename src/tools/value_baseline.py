"""
Tool: thinkneo_set_baseline
Define the pre-AI cost baseline for a business process so the system can calculate ROI.
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
        name="thinkneo_set_baseline",
        description=(
            "Define the pre-AI cost baseline for a business process. "
            "Example: 'customer_support_ticket costs $12 per ticket and takes 15 minutes without AI'. "
            "This baseline is used to calculate ROI when agents handle the same process. "
            "Call this once per process to establish the comparison point."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_set_baseline(
        process_name: Annotated[str, Field(description="Name of the business process, e.g. 'customer_support_ticket', 'loan_review', 'content_moderation'")],
        cost_per_unit_usd: Annotated[float, Field(description="Pre-AI cost per unit in USD, e.g. 12.00 for a $12 support ticket")],
        unit_label: Annotated[str, Field(description="What one unit represents, e.g. 'ticket', 'review', 'decision', 'document'")] = "unit",
        avg_duration_minutes: Annotated[Optional[float], Field(description="Average time in minutes for one unit without AI, e.g. 15")] = None,
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        notes: Annotated[Optional[str], Field(description="Additional context about this baseline")] = None,
    ) -> str:
        """Define the pre-AI cost baseline for a business process. Example: 'customer_support_ticket costs $12 per ticket and takes 15 minutes without AI'. This baseline is used to calculate ROI when agents handle the same process."""
        token = require_auth()
        key_h = hash_key(token)
        validate_workspace(workspace)

        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO value_baselines (key_hash, workspace, process_name, cost_per_unit_usd, unit_label, avg_duration_minutes, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (key_hash, workspace, process_name)
                    DO UPDATE SET cost_per_unit_usd = EXCLUDED.cost_per_unit_usd,
                                  unit_label = EXCLUDED.unit_label,
                                  avg_duration_minutes = EXCLUDED.avg_duration_minutes,
                                  notes = EXCLUDED.notes,
                                  updated_at = now()
                    RETURNING id, created_at, updated_at
                """, (key_h, workspace, process_name, cost_per_unit_usd, unit_label, avg_duration_minutes, notes))
                row = cur.fetchone()
            conn.close()

            return json.dumps({
                "status": "baseline_set",
                "baseline_id": row["id"],
                "process_name": process_name,
                "cost_per_unit_usd": cost_per_unit_usd,
                "unit_label": unit_label,
                "avg_duration_minutes": avg_duration_minutes,
                "message": f"Baseline set: each '{unit_label}' in '{process_name}' costs ${cost_per_unit_usd:.2f} without AI",
                "generated_at": utcnow(),
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e), "generated_at": utcnow()}, indent=2)
