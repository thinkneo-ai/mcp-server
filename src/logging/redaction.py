"""
Log redaction engine — automatically redacts PII and secrets from log messages.

Reuses the same detection patterns from thinkneo_check (guardrails_free.py)
and thinkneo_scan_secrets (secrets.py). Zero new detection code.

Redaction tags preserve the type of sensitive data found:
  [REDACTED-PII-EMAIL]
  [REDACTED-PII-SSN]
  [REDACTED-PII-CREDIT-CARD]
  [REDACTED-PII-CPF]
  [REDACTED-PII-PHONE]
  [REDACTED-SECRET-API-KEY]
  [REDACTED-SECRET-PASSWORD]

Config:
  LOG_REDACTION=true (default: true)
  LOG_REDACTION=false (disable for local debugging)
"""

from __future__ import annotations

import os
import re
from typing import Any

# PII patterns (same as guardrails_free.py)
_PII_PATTERNS = [
    (r"\b(?:\d[ -]*?){13,19}\b", "[REDACTED-PII-CREDIT-CARD]"),
    (r"\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b", "[REDACTED-PII-CPF]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-PII-SSN]"),
    (r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", "[REDACTED-PII-EMAIL]"),
    (r"(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,5}[-.\s]?\d{4}\b", "[REDACTED-PII-PHONE]"),
]

# Secret patterns (same as secrets.py / guardrails_free.py)
_SECRET_PATTERNS = [
    (r"(?:password|passwd|pwd|secret)\s*[:=]\s*\S+", "[REDACTED-SECRET-PASSWORD]"),
    (r"(?:api[_-]?key|token|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}", "[REDACTED-SECRET-API-KEY]"),
    (r"-----BEGIN (?:RSA|DSA|EC|OPENSSH) PRIVATE KEY-----", "[REDACTED-SECRET-PRIVATE-KEY]"),
    (r"(?:sk|pk|rk)-[a-zA-Z0-9]{32,}", "[REDACTED-SECRET-API-KEY]"),
    (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED-SECRET-GITHUB-TOKEN]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED-SECRET-AWS-KEY]"),
    (r"re_[a-zA-Z0-9_]{20,}", "[REDACTED-SECRET-RESEND-KEY]"),
]

# Secrets first (higher priority), then PII
_ALL_PATTERNS = [(re.compile(p, re.IGNORECASE), tag) for p, tag in _SECRET_PATTERNS + _PII_PATTERNS]


def is_redaction_enabled() -> bool:
    """Check if log redaction is enabled (default: true)."""
    return os.getenv("LOG_REDACTION", "true").lower() not in ("false", "0", "no")


def redact(text: str) -> str:
    """
    Redact PII and secrets from a text string.
    Returns the redacted string with type-preserving tags.
    """
    if not is_redaction_enabled():
        return text

    for pattern, tag in _ALL_PATTERNS:
        text = pattern.sub(tag, text)

    return text


def redact_dict(d: dict, max_depth: int = 5) -> dict:
    """
    Recursively redact string values in a dict.
    """
    if max_depth <= 0:
        return d

    result = {}
    for key, value in d.items():
        if isinstance(value, str):
            result[key] = redact(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value, max_depth - 1)
        elif isinstance(value, list):
            result[key] = [
                redact(v) if isinstance(v, str)
                else redact_dict(v, max_depth - 1) if isinstance(v, dict)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result
