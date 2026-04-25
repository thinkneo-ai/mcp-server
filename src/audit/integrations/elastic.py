"""Elasticsearch _bulk API push integration."""

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF = [1, 2, 4]


def push_to_elastic(
    endpoint: str,
    api_key: str,
    events: list[dict[str, Any]],
    index: str = "thinkneo-audit",
) -> dict[str, Any]:
    """Push events via Elasticsearch _bulk API."""
    headers = {
        "Content-Type": "application/x-ndjson",
        "Authorization": f"ApiKey {api_key}" if api_key else "",
    }

    # Build _bulk payload
    lines = []
    for e in events:
        lines.append(json.dumps({"index": {"_index": index}}))
        lines.append(json.dumps(e, default=str))
    body = "\n".join(lines) + "\n"

    # Chunk if >5MB
    if len(body.encode("utf-8")) > 5_000_000:
        return {"status": "error", "error": "Payload exceeds 5MB — reduce period or add filters"}

    for attempt in range(MAX_RETRIES):
        try:
            url = f"{endpoint.rstrip('/')}/_bulk"
            resp = httpx.post(url, content=body, headers=headers, timeout=30)
            if resp.status_code in (200, 201):
                result = resp.json()
                return {
                    "integration": "elastic",
                    "events_sent": len(events),
                    "errors": [item for item in result.get("items", []) if "error" in item.get("index", {})],
                    "status": "success" if not result.get("errors") else "partial_failure",
                }
            elif resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF[attempt])
            else:
                return {"status": "error", "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF[attempt])
            else:
                return {"status": "error", "error": str(exc)[:200]}

    return {"status": "error", "error": "Max retries exceeded"}
