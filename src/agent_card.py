"""
Agent Card Middleware — serves /.well-known/agent.json for A2A discovery.

This makes the ThinkNEO MCP server discoverable by any A2A-compatible agent.
The agent card is auto-generated from MCP tools and served as a static JSON response.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_AGENT_CARD_PATH = Path("/app/agent.json")
_agent_card_cache: dict | None = None


def _load_agent_card() -> dict:
    global _agent_card_cache
    if _agent_card_cache is not None:
        return _agent_card_cache
    try:
        content = _AGENT_CARD_PATH.read_text(encoding="utf-8")
        _agent_card_cache = json.loads(content)
        logger.info("Loaded A2A Agent Card: %d skills", len(_agent_card_cache.get("skills", [])))
        return _agent_card_cache
    except Exception as exc:
        logger.warning("Failed to load agent card from %s: %s", _AGENT_CARD_PATH, exc)
        return {"error": "Agent card not available"}


class AgentCardMiddleware:
    """
    ASGI middleware that serves the A2A Agent Card at /.well-known/agent.json.
    All other requests pass through to the inner app.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")
            if path in ("/.well-known/agent.json", "/.well-known/agent.json/") and method == "GET":
                card = _load_agent_card()
                response = JSONResponse(
                    card,
                    status_code=200,
                    headers={
                        "Cache-Control": "public, max-age=300",
                        "Content-Type": "application/json",
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
