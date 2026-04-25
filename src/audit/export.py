"""
Audit Export Engine — queries audit data and formats for SIEM consumption.

Supports: JSON, CEF, LEEF, syslog (RFC 5424), CSV
Optional HMAC SHA-256 signing for integrity verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .formatters import FORMATTERS

logger = logging.getLogger(__name__)


def export_events(
    events: list[dict[str, Any]],
    format: str = "json",
    sign_hmac: bool = False,
    hmac_key: str = "",
) -> dict[str, Any]:
    """
    Format audit events and optionally sign with HMAC.

    Returns dict with: format, event_count, data, hmac_signature (if signed).
    """
    if format not in FORMATTERS:
        return {
            "error": f"Unknown format '{format}'. Supported: {sorted(FORMATTERS.keys())}",
        }

    formatter = FORMATTERS[format]
    formatted = formatter(events)

    result = {
        "format": format,
        "event_count": len(events),
        "data": formatted,
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    if sign_hmac and hmac_key:
        signature = hmac.new(
            hmac_key.encode("utf-8"),
            formatted.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        result["hmac_sha256"] = signature
        result["hmac_algorithm"] = "HMAC-SHA256"

    return result


def query_audit_events(
    cursor,
    key_hash: str,
    period_days: int = 7,
    event_types: Optional[list[str]] = None,
    workspace: Optional[str] = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """
    Query audit events from multiple tables.
    Returns normalized list of event dicts.
    """
    events = []

    # 1. Usage log (tool calls)
    try:
        sql = """
            SELECT tool_name, key_hash, called_at as timestamp, cost_estimate_usd as cost_usd,
                   'tool_call' as event_type
            FROM usage_log
            WHERE key_hash = %s AND called_at >= NOW() - make_interval(days => %s)
            ORDER BY called_at DESC
            LIMIT %s
        """
        cursor.execute(sql, (key_hash, period_days, limit))
        for row in cursor.fetchall():
            r = dict(row)
            r["key_prefix"] = key_hash[:8]
            events.append(r)
    except Exception as e:
        logger.debug("usage_log query failed: %s", e)

    # 2. A2A interactions
    try:
        sql = """
            SELECT from_agent, to_agent, action as event_type, task_description,
                   cost_usd, outcome, latency_ms, initiated_at as timestamp, workspace
            FROM a2a_interactions
            WHERE key_hash = %s AND initiated_at >= NOW() - make_interval(days => %s)
            ORDER BY initiated_at DESC
            LIMIT %s
        """
        cursor.execute(sql, (key_hash, period_days, limit))
        for row in cursor.fetchall():
            events.append(dict(row))
    except Exception as e:
        logger.debug("a2a_interactions query failed: %s", e)

    # Filter by event_type if specified
    if event_types:
        events = [e for e in events if e.get("event_type") in event_types]

    # Filter by workspace if specified
    if workspace:
        events = [e for e in events if e.get("workspace", "") == workspace or "workspace" not in e]

    # Sort by timestamp descending
    events.sort(key=lambda e: str(e.get("timestamp", "")), reverse=True)

    return events[:limit]
