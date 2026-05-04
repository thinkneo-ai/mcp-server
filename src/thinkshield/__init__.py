"""
ThinkShield — Forensic Defense Layer for AI Platforms
Detect. Block. Document. Prosecute.
"""

__version__ = "0.1.0"

from .types import RequestSnapshot, Decision, ThreatIntel, RuleMatch
from .engine import ThinkShieldEngine
from .config import ShieldSettings

__all__ = [
    "ThinkShieldEngine",
    "ShieldSettings",
    "RequestSnapshot",
    "Decision",
    "ThreatIntel",
    "RuleMatch",
]
