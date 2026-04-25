"""Syslog RFC 5424 formatter with structured data.

Format: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID [SD] MSG
PRI = facility(16=local0) * 8 + severity(6=info) = 134
All timestamps in UTC (timezone bug prevention).
"""

from datetime import datetime, timezone
from typing import Any

_FACILITY = 16  # local0
_SEVERITY_INFO = 6
_SEVERITY_WARNING = 4
_PRI = _FACILITY * 8 + _SEVERITY_INFO
_PRI_WARN = _FACILITY * 8 + _SEVERITY_WARNING


def _escape_sd(val: str) -> str:
    """Escape structured data value per RFC 5424: ], \\, \"."""
    return str(val).replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")


def format_syslog(events: list[dict[str, Any]]) -> str:
    lines = []
    for e in events:
        event_type = e.get("event_type", e.get("tool_name", "event"))
        is_error = "error" in str(event_type).lower() or "violation" in str(event_type).lower()
        pri = _PRI_WARN if is_error else _PRI

        # Timestamp in UTC (RFC 5424 format)
        ts = e.get("timestamp", e.get("called_at", e.get("initiated_at", "")))
        if not ts:
            ts = datetime.now(timezone.utc).isoformat()
        ts_str = str(ts).replace("+00:00", "Z")
        if not ts_str.endswith("Z") and "+" not in ts_str and "-" not in ts_str[10:]:
            ts_str += "Z"

        # Structured data
        sd_parts = []
        for key in ("tool_name", "agent_name", "key_prefix", "cost_usd",
                     "latency_ms", "outcome", "workspace"):
            val = e.get(key)
            if val is not None:
                sd_parts.append(f'{key}="{_escape_sd(str(val))}"')

        sd = f'[thinkneo {" ".join(sd_parts)}]' if sd_parts else "-"
        msg = event_type

        line = f"<{pri}>1 {ts_str} mcp.thinkneo.ai thinkneo-gateway - {event_type} {sd} {msg}"
        lines.append(line)
    return "\n".join(lines)
