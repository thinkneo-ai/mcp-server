"""
Tiny helper for the observability module — avoids circular imports with _common.
"""

from datetime import datetime, timezone


def utcnow_obs() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
