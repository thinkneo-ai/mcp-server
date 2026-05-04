"""
ThinkShield rule registry.

Each rule module exposes a list of Rule instances. The registry collects
them all at engine init time.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional

from ..types import RequestSnapshot, RuleMatch


class Rule(ABC):
    """
    Base class for a detection rule.

    Subclass and implement `evaluate()`. Return a RuleMatch if the rule
    triggers, or None if it does not.

    Rules MUST be pure CPU — no I/O, no DB, no network.
    """

    rule_id: str
    default_confidence: float
    default_severity: str  # critical | high | medium | low | info

    @abstractmethod
    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        ...

    def _match(self, reason: str) -> RuleMatch:
        """Convenience: create a RuleMatch with this rule's defaults."""
        return RuleMatch(
            rule_id=self.rule_id,
            confidence=self.default_confidence,
            severity=self.default_severity,
            reason=reason,
        )


class RegexRule(Rule):
    """
    Rule that matches one or more regex patterns against a text target.
    Patterns are compiled once at construction for speed.
    """

    rule_id: str
    default_confidence: float
    default_severity: str
    patterns: list[re.Pattern]
    reason_template: str  # e.g., "Prompt injection pattern detected"

    def __init__(
        self,
        rule_id: str,
        patterns: list[str],
        confidence: float,
        severity: str,
        reason: str,
        flags: int = re.IGNORECASE,
    ):
        self.rule_id = rule_id
        self.default_confidence = confidence
        self.default_severity = severity
        self.reason_template = reason
        self.patterns = [re.compile(p, flags) for p in patterns]

    def _get_text(self, request: RequestSnapshot) -> str:
        """Override in subclasses to target different fields."""
        body_str = request.body.decode("utf-8", errors="replace") if request.body else ""
        return f"{request.path} {body_str}"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        text = self._get_text(request)
        for pattern in self.patterns:
            if pattern.search(text):
                return self._match(self.reason_template)
        return None


def collect_all_rules() -> list[Rule]:
    """Import and collect all rules from all rule modules."""
    from . import injection, recon, auth, abuse, headers

    all_rules: list[Rule] = []
    for module in (injection, recon, auth, abuse, headers):
        all_rules.extend(module.RULES)
    return all_rules
