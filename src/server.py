"""
ThinkNEO MCP Server
Enterprise AI Control Plane — exposed as a remote MCP server.

Transport: streamable-http
Endpoint: /mcp
Auth: Bearer token (Authorization header) for protected tools
      Public tools (provider_status, schedule_demo) work without auth.
"""

from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

from .auth import BearerTokenMiddleware
from .oauth import OAuthMiddleware
from .signup import SignupMiddleware
from .capabilities import register_prompts, register_resources
from .config import get_settings
from .landing import LANDING_HTML
from .tools import register_all

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="ThinkNEO Control Plane",
    instructions=(
        "You are connected to the ThinkNEO Enterprise AI Control Plane MCP server. "
        "ThinkNEO is the governance layer between your AI applications and providers "
        "(OpenAI, Anthropic, Google, Mistral, and more). "
        "\n\n"
        "Available tools:\n"
        "- thinkneo_read_memory: Read Claude Code project memory files (index or specific file) [public]\n"
        "- thinkneo_write_memory: Write/update project memory files [public]\n"
        "- thinkneo_check: Free prompt safety check — detects injection & PII [free]\n"
        "- thinkneo_usage: Your usage stats — calls, limits, cost [free]\n"
        "- thinkneo_check_spend: AI cost breakdown by provider/model/team [auth required]\n"
        "- thinkneo_evaluate_guardrail: Pre-flight prompt safety evaluation [auth required]\n"
        "- thinkneo_check_policy: Verify model/provider/action is allowed [auth required]\n"
        "- thinkneo_get_budget_status: Budget utilization and enforcement [auth required]\n"
        "- thinkneo_list_alerts: Active alerts and incidents [auth required]\n"
        "- thinkneo_get_compliance_status: SOC2/GDPR/HIPAA readiness [auth required]\n"
        "- thinkneo_provider_status: Real-time provider health [public]\n"
        "- thinkneo_schedule_demo: Book a demo with the ThinkNEO team [public]\n"
        "\n"
        "Free tier: 500 calls/month, auto-provisioned API key.\n"
        "For authenticated tools, users must supply a ThinkNEO API key as Bearer token.\n"
        "To get your ThinkNEO API key, visit https://thinkneo.ai/pricing\n"
        "Visit https://thinkneo.ai or contact hello@thinkneo.ai to get started."
    ),
    # stateless_http=True → each HTTP request is independent (correct for remote public API)
    stateless_http=True,
    streamable_http_path="/mcp",
    host=settings.host,
    port=settings.port,
    log_level=settings.log_level,
)

# Register all tools, prompts, and resources
register_all(mcp)
register_prompts(mcp)
register_resources(mcp)

logger.info(
    "ThinkNEO MCP Server configured: %d tools, 2 prompts, 2 resources, auth_required=%s",
    12,
    settings.require_auth,
)

# ---------------------------------------------------------------------------
# Build the ASGI app: MCP (with its own lifespan) → BearerToken → CORS
#
# IMPORTANT: we must NOT wrap the MCP Starlette app inside a new Starlette app
# via Mount, because that prevents FastMCP's lifespan (task-group init) from
# running. Instead, we stack pure-ASGI middleware directly on top of the MCP
# app so the lifespan propagates correctly.
# ---------------------------------------------------------------------------

_mcp_starlette: Starlette = mcp.streamable_http_app()


# ---------------------------------------------------------------------------
# Landing Page Middleware — serves /mcp/docs as HTML
# ---------------------------------------------------------------------------

class LandingPageMiddleware:
    """
    ASGI middleware that intercepts GET /mcp/docs and returns the developer
    landing page HTML. All other requests pass through to the inner app.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")
            if path in ("/mcp/docs", "/mcp/docs/") and method == "GET":
                response = HTMLResponse(LANDING_HTML, status_code=200)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


# Stack middleware layers (innermost first):
# 1. MCP Starlette app (handles /mcp)
# 2. Bearer token extraction (also resolves OAuth access tokens → API keys)
# 3. Landing page (/mcp/docs)
# 4. Signup (/mcp/signup)
# 5. OAuth (/.well-known/*, /oauth/*)
# 6. CORS (outermost)

_mcp_with_auth = BearerTokenMiddleware(_mcp_starlette)
_mcp_with_landing = LandingPageMiddleware(_mcp_with_auth)
_mcp_with_signup = SignupMiddleware(_mcp_with_landing)
_mcp_with_oauth = OAuthMiddleware(_mcp_with_signup)

# CORS — explicit allowlist only (never "*" with credentials, per CORS spec).
# Missing ALLOWED_ORIGINS env var now defaults to an empty list, blocking
# unconfigured cross-origin access instead of silently opening it to the world.
_cors_origins = settings.allowed_origins  # list from env, or empty list
app = CORSMiddleware(
    app=_mcp_with_oauth,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Mcp-Session-Id",
        "Mcp-Protocol-Version",
        "X-Requested-With",
    ],
    allow_credentials=True,
    max_age=600,
)
if not _cors_origins:
    logger.warning("ALLOWED_ORIGINS is empty — cross-origin browser requests will be rejected.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn

    logger.info(
        "Starting ThinkNEO MCP Server on %s:%d (log_level=%s)",
        settings.host,
        settings.port,
        settings.log_level,
    )
    uvicorn.run(
        "src.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        workers=int(os.getenv("WORKERS", "2")),
        no_server_header=True,
    )


def run_stdio() -> None:
    """Run the MCP server in stdio transport mode (used by mcp-proxy / Glama inspection)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
