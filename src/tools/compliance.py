"""
Tool: thinkneo_get_compliance_status
Returns compliance and audit readiness status for a workspace.
Requires authentication.
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ._common import demo_note, utcnow, validate_workspace

_FRAMEWORK_CONTROLS = {
    "soc2": {
        "name": "SOC 2 Type II",
        "total_controls": 64,
        "categories": ["Security", "Availability", "Confidentiality", "Processing Integrity", "Privacy"],
    },
    "gdpr": {
        "name": "GDPR",
        "total_controls": 32,
        "categories": ["Data Minimization", "Consent", "Data Subject Rights", "Breach Notification"],
    },
    "hipaa": {
        "name": "HIPAA",
        "total_controls": 45,
        "categories": ["Administrative", "Physical", "Technical", "Organizational"],
    },
    "general": {
        "name": "ThinkNEO General AI Governance",
        "total_controls": 28,
        "categories": ["Access Control", "Audit Trail", "Guardrails", "Budget Controls", "Policy Enforcement"],
    },
}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_get_compliance_status",
        description=(
            "Get compliance and audit readiness status for a workspace. "
            "Shows governance score, pending actions, and compliance gaps. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_get_compliance_status(
        workspace: Annotated[str, Field(description="Workspace name or ID to evaluate compliance readiness for")],
        framework: Annotated[str, Field(description="Compliance framework to assess: soc2 (SOC 2 Type II), gdpr (GDPR), hipaa (HIPAA), or general (ThinkNEO AI governance)")] = "general",
    ) -> str:
        """Get compliance and audit readiness status for a workspace. Shows governance score, pending actions, and compliance gaps."""
        require_auth()
        workspace = validate_workspace(workspace)

        if framework not in _FRAMEWORK_CONTROLS:
            framework = "general"

        fw = _FRAMEWORK_CONTROLS[framework]

        result = {
            "workspace": workspace,
            "framework": framework,
            "framework_name": fw["name"],
            "governance_score": 0,
            "score_out_of": 100,
            "status": "not-configured",
            "controls": {
                "total": fw["total_controls"],
                "passing": 0,
                "failing": 0,
                "not_applicable": 0,
                "not_tested": fw["total_controls"],
            },
            "categories": {cat: {"status": "not-configured"} for cat in fw["categories"]},
            "audit_trail": {
                "enabled": False,
                "retention_days": 0,
                "immutable": False,
            },
            "rbac": {
                "configured": False,
                "roles_defined": 0,
                "mfa_required": False,
            },
            "guardrails": {
                "active_policies": 0,
                "enforce_mode": False,
            },
            "pending_actions": [
                "Enable audit trail logging",
                "Configure RBAC roles",
                "Activate guardrail policies",
                "Set budget limits",
            ],
            "evaluated_at": utcnow(),
            "compliance_url": f"https://thinkneo.ai/workspaces/{workspace}/compliance",
            "trust_center": "https://thinkneo.ai/trust",
            "_demo": demo_note(workspace),
        }

        return json.dumps(result, indent=2)
