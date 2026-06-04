"""
Auth — Bearer token extraction and validation.

Uses a ContextVar so tools can read the token without needing the HTTP request
directly. The BearerTokenMiddleware sets it for every inbound HTTP request.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

from .config import get_settings
from .security import set_client_ip as _set_ip

# Per-request Bearer token storage
_bearer_token: ContextVar[Optional[str]] = ContextVar("bearer_token", default=None)


def get_bearer_token() -> Optional[str]:
    """Return the raw Bearer token for the current request, or None."""
    return _bearer_token.get()


def is_authenticated() -> bool:
    """Return True if the current request carries a valid API key."""
    token = _bearer_token.get()
    if not token:
        return False
    settings = get_settings()
    if not settings.require_auth:
        # No keys configured → accept any non-empty token (dev/demo mode)
        return True
    return token in settings.valid_api_keys


def require_auth() -> str:
    """
    Assert that the current request is authenticated.
    Returns the token on success.
    Raises ValueError with a user-friendly message on failure.
    """
    if not is_authenticated():
        raise ValueError(
            "Authentication required. Include a valid ThinkNEO API key as a Bearer token: "
            "'Authorization: Bearer <api-key>'. "
            "Request access at https://thinkneo.ai or contact hello@thinkneo.ai."
        )
    return _bearer_token.get()  # type: ignore[return-value]


class BearerTokenMiddleware:
    """
    Lightweight ASGI middleware that reads the Authorization header and stores
    the Bearer token in a ContextVar for the duration of each request.

    Must wrap the MCP app — not replace FastMCP's own middleware stack.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            raw_auth: str = headers.get(b"authorization", b"").decode("utf-8", errors="ignore")
            token: Optional[str] = None
            if raw_auth.lower().startswith("bearer "):
                token = raw_auth[7:].strip() or None
            # Extract client IP from headers or ASGI scope
            _raw_ip = (
                headers.get(b"x-real-ip", b"").decode("utf-8", errors="ignore")
                or headers.get(b"x-forwarded-for", b"").decode("utf-8", errors="ignore").split(",")[0].strip()
                or (scope.get("client") or ("unknown",))[0]
            ) or "unknown"
            _set_ip(_raw_ip)
            ctx_token = _bearer_token.set(token)
            try:
                await self.app(scope, receive, send)
            finally:
                _bearer_token.reset(ctx_token)
        else:
            await self.app(scope, receive, send)
