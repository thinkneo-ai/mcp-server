"""Generic webhook push — covers Chronicle, custom SIEMs, and any HTTP endpoint."""

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF = [1, 2, 4]


def push_to_webhook(
    endpoint: str,
    auth_header: str = "",
    events: list[dict[str, Any]] = [],
    format: str = "json",
) -> dict[str, Any]:
    """Push events to any HTTP endpoint as JSON array."""
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    body = json.dumps({"events": events, "source": "thinkneo-mcp-gateway", "count": len(events)}, default=str)

    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.post(endpoint, content=body, headers=headers, timeout=15)
            if resp.status_code in (200, 201, 202, 204):
                return {"integration": "webhook", "events_sent": len(events), "status": "success"}
            elif resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF[attempt])
            else:
                return {"status": "error", "error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF[attempt])
            else:
                return {"status": "error", "error": str(exc)[:200]}

    return {"status": "error", "error": "Max retries exceeded"}
