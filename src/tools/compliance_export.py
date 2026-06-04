"""
Tool: thinkneo_compliance_generate — live brain API.
Generates compliance reports for regulatory frameworks.
"""
from __future__ import annotations
import json
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow, validate_workspace


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_compliance_generate",
        description=(
            "Generate a compliance report for regulatory frameworks "
            "(EU AI Act, ISO 42001, SOC2, NIST). Exports from live audit data."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_compliance_generate(
        workspace: Annotated[str, Field(description="Workspace identifier")] = "default",
        format: Annotated[str, Field(description="Output format: ndjson or csv")] = "ndjson",
        framework: Annotated[str, Field(description="Framework: eu-ai-act, iso-42001, soc2, nist")] = "eu-ai-act",
    ) -> str:
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()
        params = {"format": format, "framework": framework}
        result = await brain_get("/v1/audit/events/export", params=params, token=token)
        if is_error(result):
            return json.dumps({"source": "live_gateway", "workspace": workspace,
                               "framework": framework, "format": format,
                               "report": [], "total_events": 0,
                               "note": "No audit events found for this tenant/period.",
                               "generated_at": utcnow()}, indent=2)
        return json.dumps({"source": "live_gateway", "workspace": workspace,
                           "framework": framework, "format": format,
                           "report": result, "generated_at": utcnow()}, indent=2)
