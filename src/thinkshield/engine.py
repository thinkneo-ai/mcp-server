"""
ThinkShield Detection Engine.

Pure function: given a RequestSnapshot, returns a Decision.
No I/O, no DB, no network calls. Target: <5ms p99.

Scoring:
  - confidence = max of all match confidences (NOT sum)
  - severity = highest severity among matches
  - action = block if conf >= block_threshold, alert if >= alert_threshold, else allow
"""

from __future__ import annotations

import time
from typing import Optional

from .config import ShieldSettings
from .rules import Rule, collect_all_rules
from .types import Decision, RequestSnapshot, RuleMatch

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class ThinkShieldEngine:
    """
    Stateless detection engine. Instantiate once at startup with settings,
    then call evaluate() for each request.
    """

    def __init__(self, settings: Optional[ShieldSettings] = None) -> None:
        self.settings = settings or ShieldSettings()
        self._rules: list[Rule] = self._load_rules()

    def _load_rules(self) -> list[Rule]:
        """Load all rules, filtering out disabled ones."""
        all_rules = collect_all_rules()
        enabled = [
            r for r in all_rules
            if self.settings.is_rule_enabled(r.rule_id)
        ]
        return enabled

    def evaluate(self, request: RequestSnapshot) -> Decision:
        """
        Evaluate a request against all loaded rules.

        Pure function. No I/O. <5ms p99 budget.
        """
        if not self.settings.enabled:
            return Decision(
                action="allow",
                confidence=0.0,
                severity="info",
                rule_ids=[],
                reasons=[],
                detection_ms=0.0,
            )

        t0 = time.monotonic()

        matches: list[RuleMatch] = []
        for rule in self._rules:
            match = rule.evaluate(request)
            if match is not None:
                match = self._apply_overrides(rule.rule_id, match)
                matches.append(match)

        detection_ms = (time.monotonic() - t0) * 1000.0

        if not matches:
            return Decision(
                action="allow",
                confidence=0.0,
                severity="info",
                rule_ids=[],
                reasons=[],
                detection_ms=detection_ms,
            )

        # Aggregate: max confidence, highest severity
        max_confidence = max(m.confidence for m in matches)
        max_severity = max(
            matches,
            key=lambda m: _SEVERITY_ORDER.get(m.severity, 0),
        ).severity
        rule_ids = [m.rule_id for m in matches]
        reasons = [m.reason for m in matches]

        # Apply thresholds
        if max_confidence >= self.settings.block_threshold:
            action = "block"
        elif max_confidence >= self.settings.alert_threshold:
            action = "alert"
        else:
            action = "allow"

        return Decision(
            action=action,
            confidence=max_confidence,
            severity=max_severity,
            rule_ids=rule_ids,
            reasons=reasons,
            detection_ms=detection_ms,
        )

    def _apply_overrides(self, rule_id: str, match: RuleMatch) -> RuleMatch:
        """Apply per-rule confidence/severity overrides from config."""
        conf_override = self.settings.get_confidence_override(rule_id)
        sev_override = self.settings.get_severity_override(rule_id)

        if conf_override is None and sev_override is None:
            return match

        return RuleMatch(
            rule_id=match.rule_id,
            confidence=conf_override if conf_override is not None else match.confidence,
            severity=sev_override if sev_override is not None else match.severity,
            reason=match.reason,
        )

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def rule_ids(self) -> list[str]:
        return [r.rule_id for r in self._rules]
