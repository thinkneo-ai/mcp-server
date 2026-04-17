"""
Auth — Bearer token extraction and validation.

Uses a ContextVar so tools can read the token without needing the HTTP request
directly. The BearerTokenMiddleware sets it for every inbound HTTP request.
Also captures client IP for IP allowlist enforcement.
"""

from __future__ import annotations

import hmac
from contextvars import ContextVar
from typing import Optional

from starlette.types import ASGIApp, Receive, Scope, Send

from .config import get_settings

# Per-request Bearer token storage
_bearer_token: ContextVar[Optional[str]] = ContextVar("bearer_token", default=None)


def get_bearer_token() -> Optional[str]:
    """Return the raw Bearer token for the current request, or None."""
    return _bearer_token.get()


def is_authenticated() -> bool:
    """Return True if the current request carries a valid API key.

    Uses hmac.compare_digest for constant-time comparison to prevent
    timing attacks that could be used to recover keys character-by-character.
    """
    token = _bearer_token.get()
    if not token:
        return False
    settings = get_settings()
    if not settings.require_auth:
        # No keys configured → accept any non-empty token (dev/demo mode)
        return True
    # Iterate all valid keys with constant-time comparison.
    matched = False
    for valid_key in settings.valid_api_keys:
        if hmac.compare_digest(token, valid_key):
            matched = True
    return matched


def require_auth() -> str:
    """Assert authenticated. Returns token. Raises ValueError on failure."""
    if not is_authenticated():
        raise ValueError(
            "Authentication required. Include a valid ThinkNEO API key as a Bearer token: "
            "'Authorization: Bearer <api-key>'. "
            "Request access at https://thinkneo.ai or contact hello@thinkneo.ai."
        )
    return _bearer_token.get()  # type: ignore[return-value]


def _extract_client_ip(scope: Scope) -> Optional[str]:
    """Extract client IP from X-Forwarded-For or scope['client']."""
    headers = {k.lower(): v for k, v in scope.get("headers", [])}
    xff = headers.get(b"x-forwarded-for", b"").decode("utf-8", errors="ignore")
    if xff:
        # First in the chain = client
        return xff.split(",")[0].strip()
    real_ip = headers.get(b"x-real-ip", b"").decode("utf-8", errors="ignore")
    if real_ip:
        return real_ip.strip()
    # Fallback to ASGI client
    client = scope.get("client")
    if client and isinstance(client, (tuple, list)) and len(client) > 0:
        return str(client[0])
    return None


class BearerTokenMiddleware:
    """
    Lightweight ASGI middleware that reads the Authorization header and stores
    the Bearer token in a ContextVar for the duration of each request.
    Also captures client IP for IP allowlist enforcement.
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

            # Resolve OAuth access tokens → underlying ThinkNEO API key.
            if token and not token.startswith("tnk_"):
                try:
                    from .oauth import resolve_oauth_access_token
                    resolved = resolve_oauth_access_token(token)
                    if resolved:
                        token = resolved
                except Exception:
                    pass

            # Capture client IP for security module
            client_ip = _extract_client_ip(scope)

            ctx_token = _bearer_token.set(token)
            ctx_ip = None
            try:
                # Set client_ip for security checks — lazy import to avoid circular
                try:
                    from .security import set_client_ip
                    set_client_ip(client_ip)
                except Exception:
                    pass
                await self.app(scope, receive, send)
            finally:
                _bearer_token.reset(ctx_token)
        else:
            await self.app(scope, receive, send)
