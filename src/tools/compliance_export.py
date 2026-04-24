"""
Tools: Compliance Export — One-click regulatory reports

2 MCP tools:
  - thinkneo_compliance_generate: Generate a compliance report (LGPD, ISO 42001, EU AI Act)
  - thinkneo_compliance_list: List previously generated reports
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth
from ..compliance_export import generate_compliance_report, list_compliance_reports
from .._common_obs import utcnow_obs


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="thinkneo_compliance_generate",
        description=(
            "Generate a compliance report for a regulatory framework. Aggregates data from "
            "all ThinkNEO layers (Trust Score, guardrails, PII, observability, policies, "
            "outcome validation) into a framework-specific report with compliance scoring, "
            "findings, and gap analysis. Supported frameworks: 'lgpd' (LGPD Brazil), "
            "'iso_42001' (ISO 42001 AI Management), 'eu_ai_act' (EU AI Act). "
            "Returns SHA-256 signed, tamper-evident report. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_compliance_generate(
        framework: Annotated[str, Field(
            description="Regulatory framework: 'lgpd', 'iso_42001', or 'eu_ai_act'"
        )],
        days: Annotated[int, Field(
            description="Number of days to include in the report (default 30, max 365)"
        )] = 30,
    ) -> str:
        token = require_auth()
        d = min(max(days, 1), 365)

        result = generate_compliance_report(api_key=token, framework=framework, days=d)
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_compliance_list",
        description=(
            "List previously generated compliance reports. Shows framework, period, "
            "compliance score, and download URL for each report. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_compliance_list(
        limit: Annotated[int, Field(description="Max reports to return (default 20)")] = 20,
    ) -> str:
        token = require_auth()

        result = list_compliance_reports(api_key=token, limit=min(limit, 100))
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)
