"""Log Event Extended Format (LEEF) formatter — IBM QRadar native.

Format: LEEF:2.0|Vendor|Product|Version|EventID|<tab-separated extensions>
LEEF 2.0 uses tab delimiter for extensions (vs LEEF 1.0 which uses pipe).
"""

from typing import Any

_VERSION = "3.11"
_TAB = "\t"


def _escape(val: str) -> str:
    """Escape LEEF extension value (tabs and newlines)."""
    return str(val).replace("\t", " ").replace("\n", "\\n").replace("\r", "")


def format_leef(events: list[dict[str, Any]]) -> str:
    lines = []
    for e in events:
        event_id = e.get("event_type", e.get("tool_name", "unknown"))

        ext_parts = []
        ts = e.get("timestamp", e.get("called_at", e.get("initiated_at", "")))
        if ts:
            ext_parts.append(f"devTime={_escape(str(ts))}")

        for key, leef_key in [
            ("tool_name", "action"), ("agent_name", "usrName"),
            ("key_prefix", "accountName"), ("workspace", "resource"),
            ("outcome", "outcome"), ("cost_usd", "cost"),
            ("latency_ms", "responseTime"), ("from_agent", "srcHostName"),
            ("to_agent", "dstHostName"),
        ]:
            val = e.get(key)
            if val is not None:
                ext_parts.append(f"{leef_key}={_escape(str(val))}")

        ext = _TAB.join(ext_parts)
        line = f"LEEF:2.0|ThinkNEO|MCP Gateway|{_VERSION}|{event_id}|{ext}"
        lines.append(line)
    return "\n".join(lines)
