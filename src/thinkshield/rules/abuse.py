"""
ThinkShield abuse detection rules.

Detects abusive use of legitimate API paths: destructive intent,
exfiltration patterns, tool-chain anomalies.
"""

from __future__ import annotations

from typing import Optional

from . import RegexRule, Rule, RuleMatch
from ..types import RequestSnapshot


class _BodyRegexRule(RegexRule):
    """RegexRule that searches request body only."""

    def _get_text(self, request: RequestSnapshot) -> str:
        return request.body.decode("utf-8", errors="replace") if request.body else ""


# ---------------------------------------------------------------------------
# abuse.destructive_intent — body suggesting destructive operations
# ---------------------------------------------------------------------------
_destructive_intent = _BodyRegexRule(
    rule_id="abuse.destructive_intent",
    confidence=0.75,
    severity="high",
    reason="Request body contains patterns suggesting destructive operations",
    patterns=[
        r"(drop|truncate|delete)\s+(all\s+)?(table|database|collection|index)",
        r"rm\s+-rf\s+/",
        r"(destroy|wipe|erase)\s+(all|every|entire)\s+(data|record|file|database)",
        r"format\s+(c:|disk|drive|volume)",
        r"shutdown\s+(now|immediate|-h)",
        r"kill\s+-9\s+",
    ],
)

# ---------------------------------------------------------------------------
# abuse.exfiltration_pattern — body suggesting data extraction
# ---------------------------------------------------------------------------
_exfiltration_pattern = _BodyRegexRule(
    rule_id="abuse.exfiltration_pattern",
    confidence=0.70,
    severity="high",
    reason="Request body contains patterns suggesting data exfiltration",
    patterns=[
        r"(dump|export|download|extract)\s+(all|every|complete|entire)\s+(data|code|source|database|table|record)",
        r"(print|show|list)\s+(all|every)\s+(user|customer|account|credential|password|secret|key)",
        r"SELECT\s+\*\s+FROM\s+\w+",
        r"(share|send|upload)\s+(the\s+)?(internal|proprietary|confidential)\s+(code|data|document)",
        r"base64\s+(encode|decode)\s+.{100,}",
    ],
)


# ---------------------------------------------------------------------------
# abuse.tool_chain_anomaly — STUB (deferred to MS-3)
# ---------------------------------------------------------------------------
# Full chain logic needs per-IP state tracking (sequence of tool calls
# over time). In MS-1, this is a skeleton that never matches.
# AMBIGUITY SURFACED: What constitutes a "chain anomaly" without state?
# Decision: defer entirely. Rule exists for namespace reservation.

class ToolChainAnomalyRule(Rule):
    """
    Detects tool-chain abuse patterns (e.g., calling tools_list followed by
    systematic invocation of every tool). Requires per-IP state tracking.

    MS-1: stub — always returns None.
    MS-3: will be implemented with IP state table.
    """

    rule_id = "abuse.tool_chain_anomaly"
    default_confidence = 0.60
    default_severity = "medium"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        # Deferred to MS-3 — requires IP state table for windowed analysis
        return None


RULES: list[Rule] = [
    _destructive_intent,
    _exfiltration_pattern,
    ToolChainAnomalyRule(),
]
