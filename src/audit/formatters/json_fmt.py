"""JSON formatter — structured JSON lines (one JSON object per line)."""

import json
from typing import Any


def format_json(events: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(e, default=str, ensure_ascii=False) for e in events)
