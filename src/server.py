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

from .auth import BearerTokenMiddleware
from .capabilities import register_prompts, register_resources
from .config import get_settings
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
        "- thinkneo_check_spend: AI cost breakdown by provider/model/team [auth required]\n"
        "- thinkneo_evaluate_guardrail: Pre-flight prompt safety evaluation [auth required]\n"
        "- thinkneo_check_policy: Verify model/provider/action is allowed [auth required]\n"
        "- thinkneo_get_budget_status: Budget utilization and enforcement [auth required]\n"
        "- thinkneo_list_alerts: Active alerts and incidents [auth required]\n"
        "- thinkneo_get_compliance_status: SOC2/GDPR/HIPAA readiness [auth required]\n"
        "- thinkneo_provider_status: Real-time provider health [public]\n"
        "- thinkneo_schedule_demo: Book a demo with the ThinkNEO team [public]\n"
        "\n"
        "For authenticated tools, users must supply a ThinkNEO API key via Bearer token.\n"
        "To get your ThinkNEO API key, request access at https://thinkneo.ai/talk-sales\n"
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
    8,
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

# Bearer token extraction — raw ASGI middleware (innermost layer)
_mcp_with_auth = BearerTokenMiddleware(_mcp_starlette)

# CORS — instantiate CORSMiddleware as a raw ASGI wrapper (preserves lifespan)
app = CORSMiddleware(
    app=_mcp_with_auth,
    allow_origins=settings.allowed_origins or ["*"],
    allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)


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


if __name__ == "__main__":
    main()
