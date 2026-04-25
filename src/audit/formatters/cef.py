"""Common Event Format (CEF) formatter — ArcSight, QRadar, Splunk CIM.

Format: CEF:0|Vendor|Product|Version|EventID|Name|Severity|Extension
Special chars in values: \ → \\, | → \|, = → \= (in extension keys only)
"""

from typing import Any

_VERSION = "3.11"


def _escape_header(val: str) -> str:
    """Escape CEF header field (pipes and backslashes)."""
    return str(val).replace("\\", "\\\\").replace("|", "\\|")


def _escape_ext(val: str) -> str:
    """Escape CEF extension value (equals and backslashes)."""
    return str(val).replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n")


def _severity(event: dict) -> int:
    """Map event to CEF severity (0-10)."""
    etype = event.get("event_type", event.get("tool_name", ""))
    if "error" in etype or "violation" in etype:
        return 7
    if "guardrail" in etype or "pii" in etype:
        return 6
    return 3


def format_cef(events: list[dict[str, Any]]) -> str:
    lines = []
    for e in events:
        event_id = e.get("event_type", e.get("tool_name", "unknown"))
        name = _escape_header(e.get("event_type", "event"))
        sev = _severity(e)

        ext_parts = []
        for key in ("tool_name", "agent_name", "key_prefix", "workspace",
                     "outcome", "cost_usd", "latency_ms", "from_agent", "to_agent"):
            val = e.get(key)
            if val is not None:
                ext_parts.append(f"{key}={_escape_ext(str(val))}")

        ts = e.get("timestamp", e.get("called_at", e.get("initiated_at", "")))
        if ts:
            ext_parts.insert(0, f"rt={_escape_ext(str(ts))}")

        ext = " ".join(ext_parts)
        line = f"CEF:0|ThinkNEO|MCP Gateway|{_VERSION}|{_escape_header(event_id)}|{name}|{sev}|{ext}"
        lines.append(line)
    return "\n".join(lines)
