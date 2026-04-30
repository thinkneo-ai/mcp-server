"""
ThinkShield authentication detection rules.

Detects credential probing, token format anomalies, and common
test credentials.
"""

from __future__ import annotations

import re
from typing import Optional

from . import Rule, RuleMatch
from ..types import RequestSnapshot


# ---------------------------------------------------------------------------
# auth.empty_bearer — Authorization header present but empty/whitespace
# ---------------------------------------------------------------------------
class EmptyBearerRule(Rule):
    rule_id = "auth.empty_bearer"
    default_confidence = 0.50
    default_severity = "medium"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        if "authorization" not in request.headers:
            return None  # no header at all — not suspicious per se
        auth = request.headers["authorization"]
        stripped = auth.strip()
        if not stripped:
            return self._match("Authorization header present but value is empty")
        if stripped.lower() in ("bearer", "bearer "):
            return self._match("Authorization header present but bearer token is empty")
        return None


# ---------------------------------------------------------------------------
# auth.malformed_bearer — token format obviously wrong
# ---------------------------------------------------------------------------
class MalformedBearerRule(Rule):
    rule_id = "auth.malformed_bearer"
    default_confidence = 0.45
    default_severity = "medium"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        auth = request.headers.get("authorization", "")
        if not auth or not auth.lower().startswith("bearer "):
            return None
        token = auth[7:].strip()
        if not token:
            return None  # handled by empty_bearer

        # Token too short (< 8 chars) — likely a probe
        if len(token) < 8:
            return self._match("Bearer token suspiciously short (< 8 characters)")

        # Token contains spaces — malformed
        if " " in token:
            return self._match("Bearer token contains spaces (malformed)")

        # Token contains control characters
        if any(ord(c) < 32 for c in token):
            return self._match("Bearer token contains control characters")

        return None


# ---------------------------------------------------------------------------
# auth.token_probe — common test/default tokens
# ---------------------------------------------------------------------------
_TEST_TOKENS = {
    "test", "admin", "root", "password", "null", "undefined", "none",
    "token", "secret", "default", "changeme", "1234", "12345", "123456",
    "apikey", "api_key", "api-key", "key", "demo", "example", "sample",
    "bearer", "access_token", "foobar", "foo", "bar", "baz",
}


class TokenProbeRule(Rule):
    rule_id = "auth.token_probe"
    default_confidence = 0.70
    default_severity = "high"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        auth = request.headers.get("authorization", "")
        if not auth:
            return None
        # Extract the token part
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip().lower()
        else:
            token = auth.strip().lower()
        if not token:
            return None
        if token in _TEST_TOKENS:
            return self._match("Common test/default credential detected")
        return None


# ---------------------------------------------------------------------------
# auth.credential_stuffing_pattern — rapid distinct auth values
# ---------------------------------------------------------------------------
# Phase 1: stateless heuristic — we check for raw hex hashes as tokens,
# which suggest automated credential testing rather than legitimate use.
# Full windowed tracking deferred to MS-3 (IP state table).

_RAW_HEX = re.compile(r"^[a-f0-9]{32,128}$", re.IGNORECASE)


class CredentialStuffingRule(Rule):
    rule_id = "auth.credential_stuffing_pattern"
    default_confidence = 0.35
    default_severity = "medium"

    def evaluate(self, request: RequestSnapshot) -> Optional[RuleMatch]:
        auth = request.headers.get("authorization", "")
        if not auth:
            return None
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        else:
            token = auth.strip()
        if not token:
            return None
        # Raw hex hash as token — suggests automated probing
        if _RAW_HEX.match(token):
            return self._match(
                "Bearer token appears to be a raw hex hash (possible automated credential testing)"
            )
        return None


RULES: list[Rule] = [
    EmptyBearerRule(),
    MalformedBearerRule(),
    TokenProbeRule(),
    CredentialStuffingRule(),
]
