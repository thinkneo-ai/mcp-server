"""
Tool Call Logger — logs every MCP tool invocation with:
  - Tool name
  - Client IP + estimated region
  - Session call count
  - Timestamp
  - Auth status
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger("mcp.tool_logger")

# ── Per-request IP storage (set by middleware) ──────────────────────────────
_client_ip: ContextVar[str] = ContextVar("client_ip", default="unknown")

def get_client_ip() -> str:
    return _client_ip.get()

def set_client_ip(ip: str) -> None:
    _client_ip.set(ip)

# ── Session tracking ────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}
_sessions_lock = Lock()
SESSION_TTL = 3600  # 1 hour

def _get_session(ip: str) -> dict:
    now = time.time()
    with _sessions_lock:
        # Cleanup expired
        expired = [k for k, v in _sessions.items() if now - v["last"] > SESSION_TTL]
        for k in expired:
            del _sessions[k]
        # Get or create
        if ip not in _sessions:
            _sessions[ip] = {"calls": 0, "tools": defaultdict(int), "first": now, "last": now}
        s = _sessions[ip]
        s["last"] = now
        return s

# ── IP to region (lightweight, no external API) ─────────────────────────────
_IP_RANGES = {
    "10.": "Private", "172.": "Private", "192.168.": "Private", "127.": "Localhost",
    "100.": "Tailscale",
    "35.": "GCP", "34.": "AWS", "52.": "AWS", "54.": "AWS",
    "13.": "AWS", "18.": "AWS", "3.": "AWS",
    "20.": "Azure", "40.": "Azure", "104.": "Azure/Cloudflare",
    "142.250.": "Google", "172.217.": "Google", "216.58.": "Google",
    "157.240.": "Meta", "31.13.": "Meta",
    "185.": "EU-likely", "176.": "EU-likely", "178.": "EU-likely",
    "170.": "LATAM-likely", "186.": "LATAM-likely", "187.": "LATAM-likely", "189.": "LATAM-likely", "200.": "LATAM-likely", "201.": "LATAM-likely",
    "1.": "APAC-likely", "14.": "APAC-likely", "27.": "APAC-likely", "36.": "APAC-likely",
    "41.": "Africa-likely", "105.": "Africa-likely",
}

def _estimate_region(ip: str) -> str:
    for prefix, region in _IP_RANGES.items():
        if ip.startswith(prefix):
            return region
    return "Unknown"

# ── Log file ────────────────────────────────────────────────────────────────
LOG_DIR = Path("/data/logs")
LOG_FILE = LOG_DIR / "tool_calls.jsonl"

def _append_log(entry: dict) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.warning("Failed to write tool log: %s", e)

# ── Main logging function ───────────────────────────────────────────────────

def log_tool_call(tool_name: str, args: dict | None = None, auth: bool = False) -> None:
    """Log a tool call with full context."""
    ip = get_client_ip()
    region = _estimate_region(ip)
    session = _get_session(ip)
    session["calls"] += 1
    session["tools"][tool_name] += 1

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "ip": ip,
        "region": region,
        "auth": auth,
        "session_call_num": session["calls"],
        "session_tool_counts": dict(session["tools"]),
        "args_summary": {k: str(v)[:50] for k, v in (args or {}).items()},
    }

    _append_log(entry)

    logger.info(
        "TOOL_CALL | %s | ip=%s region=%s | auth=%s | session_call=#%d | args=%s",
        tool_name, ip, region, auth, session["calls"],
        json.dumps(entry.get("args_summary", {})),
    )


# ── ASGI Middleware to extract client IP ────────────────────────────────────

from starlette.types import ASGIApp, Receive, Scope, Send

class ClientIPMiddleware:
    """Extract client IP from X-Real-IP / X-Forwarded-For / REMOTE_ADDR."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            # Prefer X-Real-IP (set by nginx)
            ip = (
                headers.get(b"x-real-ip", b"").decode("utf-8", errors="ignore")
                or headers.get(b"x-forwarded-for", b"").decode("utf-8", errors="ignore").split(",")[0].strip()
                or (scope.get("client") or ("unknown",))[0]
            )
            token = _client_ip.set(ip)
            try:
                await self.app(scope, receive, send)
            finally:
                _client_ip.reset(token)
        else:
            await self.app(scope, receive, send)
