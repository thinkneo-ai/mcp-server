"""CSV formatter — simple tabular export for spreadsheets and manual audit."""

import csv
import io
from typing import Any

_COLUMNS = [
    "timestamp", "event_type", "tool_name", "agent_name",
    "key_prefix", "workspace", "outcome", "cost_usd",
    "latency_ms", "from_agent", "to_agent",
]


def format_csv(events: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for e in events:
        row = {}
        for col in _COLUMNS:
            val = e.get(col, e.get("called_at" if col == "timestamp" else col, ""))
            row[col] = str(val) if val is not None else ""
        writer.writerow(row)
    return output.getvalue()
