"""
ThinkShield reconnaissance detection rules.

Detects mapping/probing behavior: path probing, tool enumeration,
unusual HTTP methods, fingerprint probing.
"""

from __future__ import annotations

import re
from typing import Optional

from . import Rule, RuleMatch
from ..types import RequestSnapshot


# ---------------------------------------------------------------------------
# recon.path_probe — requests to well-known sensitive paths
# ---------------------------------------------------------------------------
_PROBE_PATHS: dict[str, tuple[float, str]] = {
    "/.git/": (0.85, "high"),
    "/.git/config": (0.90, "high"),
    "/.git/HEAD": (0.90, "high"),
    "/.env": (0.85, "high"),
    "/.aws/credentials": (0.90, "critical"),
    "/wp-admin": (0.60, "medium"),
    "/wp-login.php": (0.60, "medium"),
    "/wp-content": (0.50, "medium"),
    "/phpmyadmin": (0.60, "medium"),
    "/admin": (0.45, "medium"),
    "/admin/": (0.45, "medium"),
    "/swagger.json": (0.40, "low"),
    "/openapi.json": (0.40, "low"),
    "/actuator": (0.55, "medium"),
    "/actuator/env": (0.70, "high"),
    "/actuator/health": (0.40, "low"),
    "/debug/vars": (0.60, "medium"),
    "/server-status": (0.50, "medium"),
    "/server-info": (0.50, "medium"),
    "/elmah.axd": (0.55, "medium"),
    "/config.json": (0.45, "low"),
    "/config.yml": (0.45, "low"),
    "/backup": (0.45, "low"),
    "/.DS_Store": (0.35, "low"),
    "/.htaccess": (0.45, "medium"),
    "/.htpasswd": (0.70, "high"),
    "/cgi-bin/": (0.40, "low"),
    "/xmlrpc.php": (0.55, "medium"),
    "/console": (0.55, "medium"),
}


class PathProbeRule(Rule):
    rule_id = "recon.path_probe"
    default_confidence = 0.60
    default_severity = "medium"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        path_lower = request.path.lower()
        for probe_path, (confidence, severity) in _PROBE_PATHS.items():
            if path_lower == probe_path or path_lower.startswith(probe_path):
                return RuleMatch(
                    rule_id=self.rule_id,
                    confidence=confidence,
                    severity=severity,
                    reason=f"Reconnaissance: request to probe path {probe_path}",
                )
        return None


# ---------------------------------------------------------------------------
# recon.tool_enumeration — heuristic for tool surface mapping
# ---------------------------------------------------------------------------
# Phase 1: stateless heuristic — check if body contains tools/list call
# Full windowed state tracking deferred to MS-3 (IP state table)

_TOOL_ENUM_PATTERNS = re.compile(
    r"\"method\"\s*:\s*\"(tools/list|resources/list|prompts/list)\"",
    re.IGNORECASE,
)


class ToolEnumerationRule(Rule):
    rule_id = "recon.tool_enumeration"
    default_confidence = 0.25
    default_severity = "low"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        body_str = request.body.decode("utf-8", errors="replace") if request.body else ""
        if _TOOL_ENUM_PATTERNS.search(body_str):
            return self._match("Tool/resource/prompt listing call detected")
        return None


# ---------------------------------------------------------------------------
# recon.method_probe — unusual HTTP methods on MCP endpoint
# ---------------------------------------------------------------------------
_UNUSUAL_METHODS = {"TRACE", "CONNECT", "PROPFIND", "PROPPATCH", "MKCOL",
                    "COPY", "MOVE", "LOCK", "UNLOCK", "PATCH", "PURGE"}


class MethodProbeRule(Rule):
    rule_id = "recon.method_probe"
    default_confidence = 0.65
    default_severity = "medium"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        if request.method.upper() in _UNUSUAL_METHODS:
            return self._match(
                f"Unusual HTTP method {request.method} on MCP endpoint"
            )
        return None


# ---------------------------------------------------------------------------
# recon.fingerprint_probe — requests to unadvertised discovery paths
# ---------------------------------------------------------------------------
_FINGERPRINT_PATHS = re.compile(
    r"^/(\.well-known/(openid-configuration|jwks\.json|assetlinks\.json|apple-app-site-association)"
    r"|server-status|server-info|nginx_status|stub_status"
    r"|metrics|prometheus|healthz|readyz|livez)",
    re.IGNORECASE,
)


class FingerprintProbeRule(Rule):
    rule_id = "recon.fingerprint_probe"
    default_confidence = 0.45
    default_severity = "low"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        # /.well-known/agent.json is legitimate for MCP — skip it
        if request.path.lower() in ("/.well-known/agent.json",):
            return None
        if _FINGERPRINT_PATHS.match(request.path):
            return self._match(
                f"Fingerprint probe to unadvertised path {request.path}"
            )
        return None


RULES: list[Rule] = [
    PathProbeRule(),
    ToolEnumerationRule(),
    MethodProbeRule(),
    FingerprintProbeRule(),
]
