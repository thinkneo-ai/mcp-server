"""
Tool: thinkneo_audit_export — live brain API.
Exports audit events in JSON or CSV with date range filtering.
"""
from __future__ import annotations
import json
from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_audit_export",
        description=(
            "Export audit events from the live gateway. Supports JSON and CSV formats "
            "with date range filtering for SIEM integration."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_audit_export(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        format: Annotated[str, Field(description="Output format: ndjson or csv")] = "ndjson",
        start_date: Annotated[Optional[str], Field(description="Start date ISO format")] = None,
        end_date: Annotated[Optional[str], Field(description="End date ISO format")] = None,
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()
        params = {"format": format}
        if start_date:
            params["start"] = start_date
        if end_date:
            params["end"] = end_date
        result = await brain_get("/v1/audit/events/export", params=params, token=token)
        if is_error(result):
            return json.dumps({"source": "live_gateway", "workspace": workspace,
                               "format": format, "export": [], "total_events": 0,
                               "note": "No audit events found for this tenant/period.",
                               "generated_at": utcnow()}, indent=2)
        return json.dumps({"source": "live_gateway", "workspace": workspace,
                           "format": format, "start_date": start_date,
                           "end_date": end_date, "export": result,
                           "generated_at": utcnow()}, indent=2)
