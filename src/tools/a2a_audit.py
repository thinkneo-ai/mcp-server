"""
Tool: thinkneo_a2a_audit — live brain API.
Retrieves audit trail with hash verification for A2A events.
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
        name="thinkneo_a2a_audit",
        description=(
            "Retrieve immutable audit trail for A2A interactions with hash verification. "
            "Each event is cryptographically chained for tamper detection."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_a2a_audit(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        trace_id: Annotated[Optional[str], Field(description="Filter by trace ID")] = None,
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()
        params = {"limit": "100"}
        if trace_id:
            params["trace_id"] = trace_id
        events = await brain_get("/v1/audit/events", params=params, token=token)
        verify = await brain_get("/v1/audit/events/verify", params=params, token=token)
        audit = {"source": "live_gateway", "workspace": workspace, "generated_at": utcnow()}
        if not is_error(events):
            audit["events"] = events if isinstance(events, list) else events.get("events", [])
            audit["total"] = len(audit["events"])
        if not is_error(verify):
            audit["verification"] = verify
        if is_error(events) and is_error(verify):
            audit["error"] = "Could not reach audit endpoints"
            audit["detail"] = events.get("detail", "")
        return json.dumps(audit, indent=2)
