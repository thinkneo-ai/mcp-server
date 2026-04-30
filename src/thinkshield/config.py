"""
ThinkShield configuration.

All settings loaded from environment variables with THINKSHIELD_ prefix.
No I/O beyond os.getenv at import time.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache


class ShieldSettings:
    """Detection engine settings. Immutable after construction."""

    def __init__(self) -> None:
        self.enabled: bool = os.getenv("THINKSHIELD_ENABLED", "true").lower() == "true"
        self.block_threshold: float = float(os.getenv("THINKSHIELD_BLOCK_THRESHOLD", "0.7"))
        self.alert_threshold: float = float(os.getenv("THINKSHIELD_ALERT_THRESHOLD", "0.4"))
        self.body_max_bytes: int = int(os.getenv("THINKSHIELD_BODY_MAX", "8192"))

        # Per-rule overrides: JSON dict of rule_id → {enabled, confidence, severity}
        # Example: THINKSHIELD_RULE_OVERRIDES={"injection.xss": {"enabled": false}}
        raw_overrides = os.getenv("THINKSHIELD_RULE_OVERRIDES", "{}")
        try:
            self.rule_overrides: dict[str, dict] = json.loads(raw_overrides)
        except (json.JSONDecodeError, TypeError):
            self.rule_overrides = {}

    def is_rule_enabled(self, rule_id: str) -> bool:
        """Check if a specific rule is enabled (default: True)."""
        override = self.rule_overrides.get(rule_id, {})
        return override.get("enabled", True)

    def get_confidence_override(self, rule_id: str) -> float | None:
        """Get confidence override for a rule, or None to use default."""
        override = self.rule_overrides.get(rule_id, {})
        val = override.get("confidence")
        return float(val) if val is not None else None

    def get_severity_override(self, rule_id: str) -> str | None:
        """Get severity override for a rule, or None to use default."""
        override = self.rule_overrides.get(rule_id, {})
        return override.get("severity")


@lru_cache(maxsize=1)
def get_shield_settings() -> ShieldSettings:
    return ShieldSettings()
