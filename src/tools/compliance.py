"""
Tool: thinkneo_get_compliance_status
Returns compliance status from live gateway governance endpoints.
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
        name="thinkneo_get_compliance_status",
        description=(
            "Get compliance status including framework coverage (EU AI Act, ISO 42001, "
            "NIST AI RMF, SOC 2) and governance assessments from the ThinkNEO gateway."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_get_compliance_status(
        workspace: Annotated[str, Field(description="Workspace name or ID")] = "default",
        framework: Annotated[str, Field(description="Filter by framework: eu-ai-act, iso-42001, nist-ai-rmf, soc2, all")] = "all",
    ) -> str:
        """Get compliance and audit readiness status for a workspace. Shows governance score, pending actions, and compliance gaps."""
        require_auth()
        workspace = validate_workspace(workspace)
        token = get_bearer_token()

        result = {"workspace": workspace, "framework_filter": framework, "source": "live_gateway", "fetched_at": utcnow()}

        coverage = await brain_get("/v1/tenant/governance/framework-coverage", token=token)
        if not is_error(coverage):
            result["framework_coverage"] = coverage

        assessments = await brain_get("/v1/tenant/governance/assessments", token=token)
        if not is_error(assessments):
            result["assessments"] = assessments

        evidence = await brain_get("/v1/tenant/governance/evidence", token=token)
        if not is_error(evidence):
            result["evidence_count"] = len(evidence) if isinstance(evidence, list) else evidence

        mappings = await brain_get("/v1/tenant/governance/framework-mappings", token=token)
        if not is_error(mappings):
            result["framework_mappings"] = mappings

        if all(is_error(x) for x in [coverage, assessments, evidence, mappings]):
            result["error"] = "Could not reach governance endpoints"
            result["note"] = "Ensure API key has tenant governance access"

        return json.dumps(result, indent=2)
