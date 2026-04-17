"""
Shared helpers for ThinkNEO MCP tools.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

_WORKSPACE_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

# Guardrail rules — mirrors the A2A agent's governance_api.py
GUARDRAIL_RULES = [
    {
        "id": "pii-exposure-prevention",
        "name": "PII Exposure Prevention",
        "description": "Detects requests to generate or expose PII (SSN, credit cards, email, phone, etc.)",
        "severity": "critical",
        "patterns": [
            r"ssn|social security",
            r"credit card|card number|cvv|cvc",
            r"password|passwd|secret key|api.?key",
            r"passport number",
        ],
    },
    {
        "id": "prompt-injection-defense",
        "name": "Prompt Injection Defense",
        "description": "Detects attempts to override system instructions",
        "severity": "high",
        "patterns": [
            r"ignore\b.{0,20}\b(previous|prior|above|all)\b.{0,20}\binstructions",
            r"disregard\b.{0,30}\b(system|previous|instructions)",
            r"act as (an?|the) (unrestricted|jailbreak|DAN)",
            r"new instructions:",
            r"forget (everything|what you were told)",
            r"reveal\b.{0,20}\bsystem prompt",
        ],
    },
    {
        "id": "source-code-exfiltration",
        "name": "Source Code Exfiltration",
        "description": "Detects requests to extract proprietary source code from context",
        "severity": "high",
        "patterns": [
            r"print all (the |our )?(source |)?code",
            r"dump the (codebase|source|repository)",
            r"share (the |all )?(internal|proprietary) code",
        ],
    },
    {
        "id": "financial-data-protection",
        "name": "Financial Data Protection",
        "description": "Controls exposure of pricing, revenue, or financial forecasts",
        "severity": "medium",
        "patterns": [
            r"all customer (prices|pricing)",
            r"revenue breakdown",
            r"internal pricing sheet",
            r"salary|payroll|compensation data",
        ],
    },
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_workspace(ws: str) -> str:
    """Validate workspace name.

    Accepts alphanumeric + underscore + hyphen, 1-64 chars.
    On invalid input: logs a WARNING for security audit, returns "default".
    The WARN log ensures invalid queries are visible in monitoring without
    breaking existing tool callers that don't expect exceptions.
    """
    ws_clean = str(ws).strip()[:128]  # cap input length to prevent log abuse
    if not ws_clean or not _WORKSPACE_RE.match(ws_clean):
        logger.warning("Invalid workspace rejected (returning 'default'): %r",
                       ws_clean[:32])
        return "default"
    return ws_clean


def evaluate_guardrails(text: str, workspace: str) -> Dict[str, Any]:
    violations = []
    for rule in GUARDRAIL_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                violations.append(
                    {
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "severity": rule["severity"],
                        "description": rule["description"],
                        "recommendation": (
                            "Remove sensitive references and rephrase using "
                            "anonymized identifiers or approved data abstractions."
                        ),
                    }
                )
                break

    if not violations:
        status = "ALLOWED"
        risk_level = "none"
    else:
        severities = {v["severity"] for v in violations}
        if "critical" in severities:
            risk_level = "critical"
        elif "high" in severities:
            risk_level = "high"
        else:
            risk_level = "medium"
        status = "BLOCKED"

    return {
        "status": status,
        "risk_level": risk_level,
        "violations": violations,
        "policy_ref": f"workspace:{workspace}/guardrails/v1",
        "evaluated_at": utcnow(),
    }


def demo_note(workspace: str) -> str:
    return (
        f"Demo response for workspace '{workspace}'. "
        "Connect to your live ThinkNEO workspace for real data. "
        "Contact hello@thinkneo.ai to set up your account."
    )
