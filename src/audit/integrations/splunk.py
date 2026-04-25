"""Splunk HEC (HTTP Event Collector) push integration."""

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF = [1, 2, 4]


def push_to_splunk(
    endpoint: str,
    token: str,
    events: list[dict[str, Any]],
    source: str = "thinkneo-mcp-gateway",
    sourcetype: str = "_json",
    index: str = "main",
) -> dict[str, Any]:
    """
    Push events to Splunk via HEC.
    Chunks into batches if >1MB.
    Returns dict with status, events_sent, errors.
    """
    headers = {
        "Authorization": f"Splunk {token}",
        "Content-Type": "application/json",
    }

    # Build HEC payload (one JSON object per event, newline-separated)
    hec_events = []
    for e in events:
        hec_events.append(json.dumps({
            "event": e,
            "source": source,
            "sourcetype": sourcetype,
            "index": index,
            "time": e.get("timestamp", ""),
        }))

    # Chunk into 1MB batches
    batches = []
    current_batch = []
    current_size = 0
    for he in hec_events:
        size = len(he.encode("utf-8"))
        if current_size + size > 1_000_000 and current_batch:
            batches.append("\n".join(current_batch))
            current_batch = []
            current_size = 0
        current_batch.append(he)
        current_size += size
    if current_batch:
        batches.append("\n".join(current_batch))

    total_sent = 0
    errors = []

    for batch in batches:
        for attempt in range(MAX_RETRIES):
            try:
                resp = httpx.post(endpoint, content=batch, headers=headers, timeout=15)
                if resp.status_code == 200:
                    total_sent += batch.count("\n") + 1
                    break
                elif resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF[attempt])
                    continue
                else:
                    errors.append(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    break
            except Exception as exc:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF[attempt])
                else:
                    errors.append(str(exc)[:200])

    return {
        "integration": "splunk",
        "events_sent": total_sent,
        "batches": len(batches),
        "errors": errors,
        "status": "success" if not errors else "partial_failure",
    }
