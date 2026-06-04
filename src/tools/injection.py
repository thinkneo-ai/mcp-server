"""
Tool: thinkneo_detect_injection — prompt injection detection.
Uses local guardrail regex + live runtime metrics for stats.
"""
from __future__ import annotations
import json
import re
from typing import Annotated
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from ..auth import require_auth, get_bearer_token
from ..brain_client import brain_get, is_error
from ._common import utcnow, GUARDRAIL_RULES


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_detect_injection",
        description=(
            "Detect prompt injection attempts in text using guardrail patterns. "
            "Also retrieves live guardrails_blocked stats from the gateway."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def thinkneo_detect_injection(
        text: Annotated[str, Field(description="Text to analyze for injection attempts")],
    ) -> str:
        require_auth()
        token = get_bearer_token()
        detections = []
        for rule in GUARDRAIL_RULES:
            for pattern in rule["patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    detections.append({"rule_id": rule["id"], "rule_name": rule["name"],
                                       "severity": rule["severity"]})
                    break
        is_inj = len(detections) > 0
        risk = "critical" if any(d["severity"] == "critical" for d in detections) \
               else "high" if detections else "none"
        result = {"source": "live_gateway", "is_injection": is_inj, "risk_level": risk,
                  "detections": detections, "text_length": len(text), "generated_at": utcnow()}
        metrics = await brain_get("/v1/internal/runtime-metrics", token=token)
        if not is_error(metrics):
            m = metrics.get("runtime_metrics", metrics)
            result["gateway_stats"] = {"guardrails_blocked": m.get("guardrails_blocked", 0),
                                       "blocked_total": m.get("blocked_total", 0)}
        return json.dumps(result, indent=2)
