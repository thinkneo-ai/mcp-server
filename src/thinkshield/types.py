"""
ThinkShield core types.

All dataclasses are frozen (immutable) to prevent accidental mutation
during evaluation. The engine produces a Decision from a RequestSnapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass(frozen=True)
class ThreatIntel:
    """
    External threat intelligence for a source IP.
    Populated by MS-2 (threat_intel.py). In MS-1, always None.
    Engine handles None gracefully.
    """

    tor_match: bool = False
    spamhaus_match: bool = False
    abuseipdb_score: Optional[int] = None
    asn: Optional[int] = None
    asn_org: Optional[str] = None


@dataclass(frozen=True)
class RequestSnapshot:
    """
    Immutable snapshot of an incoming request, captured by the middleware
    before evaluation. This is the only input to the detection engine.
    """

    method: str
    path: str
    headers: dict[str, str]  # lowercase keys
    body: bytes  # max 8192 bytes (caller truncates)
    source_ip: str
    geo_country: Optional[str] = None  # from X-Geo-Country header
    user_agent: Optional[str] = None
    key_hash: Optional[str] = None  # may be None for unauth requests
    threat_intel: Optional[ThreatIntel] = None  # populated by MS-2


@dataclass(frozen=True)
class RuleMatch:
    """Single rule match result."""

    rule_id: str
    confidence: float  # 0.0 – 1.0
    severity: Literal["critical", "high", "medium", "low", "info"]
    reason: str  # human-readable, generic (no political context)


@dataclass(frozen=True)
class Decision:
    """
    Engine output — the action to take on a request.
    """

    action: Literal["allow", "alert", "block"]
    confidence: float  # 0.0 – 1.0
    severity: Literal["critical", "high", "medium", "low", "info"]
    rule_ids: list[str]
    reasons: list[str]
    detection_ms: float  # measured engine latency
