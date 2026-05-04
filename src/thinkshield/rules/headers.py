"""
ThinkShield header anomaly detection rules.

Detects known attack tool user-agents, missing user-agents,
suspicious automation signatures, and host mismatches.
"""

from __future__ import annotations

import re
from typing import Optional

from . import Rule, RuleMatch
from ..types import RequestSnapshot


# ---------------------------------------------------------------------------
# headers.attack_tool_ua — known offensive security tool user-agents
# ---------------------------------------------------------------------------
_ATTACK_TOOLS = re.compile(
    r"(sqlmap|nikto|nmap|masscan|gobuster|dirbuster|wfuzz|ffuf|hydra"
    r"|burpsuite|burp|zaproxy|zap|w3af|acunetix|nessus|openvas"
    r"|metasploit|nuclei|feroxbuster|dirb|skipfish|arachni)",
    re.IGNORECASE,
)


class AttackToolUARule(Rule):
    rule_id = "headers.attack_tool_ua"
    default_confidence = 0.85
    default_severity = "high"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        ua = request.user_agent or request.headers.get("user-agent", "")
        if ua and _ATTACK_TOOLS.search(ua):
            return self._match("User-Agent identifies a known attack/scanning tool")
        return None


# ---------------------------------------------------------------------------
# headers.empty_ua — missing or empty User-Agent on POST to /mcp
# ---------------------------------------------------------------------------
class EmptyUARule(Rule):
    rule_id = "headers.empty_ua"
    default_confidence = 0.30
    default_severity = "low"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        ua = request.user_agent or request.headers.get("user-agent", "")
        if not ua.strip() and request.method.upper() == "POST":
            return self._match("POST request with missing or empty User-Agent")
        return None


# ---------------------------------------------------------------------------
# headers.suspicious_ua — automation signatures in context
# ---------------------------------------------------------------------------
# python-requests, httpx, curl, wget are common for legitimate MCP clients.
# Low confidence — only flags when combined with no auth.

_AUTOMATION_UA = re.compile(
    r"(python-requests|python-httpx|python-urllib|aiohttp|Go-http-client"
    r"|Java/\d|okhttp|Apache-HttpClient)",
    re.IGNORECASE,
)


class SuspiciousUARule(Rule):
    rule_id = "headers.suspicious_ua"
    default_confidence = 0.20
    default_severity = "info"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        ua = request.user_agent or request.headers.get("user-agent", "")
        if not ua:
            return None
        if _AUTOMATION_UA.search(ua) and not request.key_hash:
            return self._match(
                "Automated HTTP client detected without authentication"
            )
        return None


# ---------------------------------------------------------------------------
# headers.host_mismatch — Host header not matching expected values
# ---------------------------------------------------------------------------
_EXPECTED_HOSTS = {
    "mcp.thinkneo.ai",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}


class HostMismatchRule(Rule):
    rule_id = "headers.host_mismatch"
    default_confidence = 0.40
    default_severity = "low"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        host = request.headers.get("host", "")
        if not host:
            return None
        # Strip port
        host_name = host.split(":")[0].lower().strip()
        if not host_name:
            return None
        # Allow localhost variants and expected hosts
        if host_name in _EXPECTED_HOSTS:
            return None
        # Allow IP addresses (direct access)
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host_name):
            return None
        # Allow Tailscale IPs (100.x.x.x)
        if host_name.startswith("100."):
            return None
        return self._match(
            f"Host header '{host_name}' does not match expected values"
        )


RULES: list[Rule] = [
    AttackToolUARule(),
    EmptyUARule(),
    SuspiciousUARule(),
    HostMismatchRule(),
]
