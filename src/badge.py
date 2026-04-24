"""
Badge Endpoint — serves SVG and JSON trust score badges.

Routes:
  GET /badge/{report_token}       → SVG badge (shields.io style)
  GET /badge/{report_token}.json  → JSON badge data

Implemented as ASGI middleware that intercepts /badge/ requests
before they reach the MCP app.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# Badge colors by level
BADGE_COLORS = {
    "platinum": "#8B5CF6",
    "gold": "#F59E0B",
    "silver": "#6B7280",
    "bronze": "#CD7F32",
    "unrated": "#9CA3AF",
}

BADGE_LABELS = {
    "platinum": "Platinum",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
    "unrated": "Unrated",
}

# Route pattern: /badge/{token} or /badge/{token}.json
_BADGE_RE = re.compile(r"^/badge/([A-Za-z0-9_\-]{20,48})(\.json)?$")


def _generate_svg(score: int, badge_level: str, org_name: str) -> str:
    """Generate a shields.io-style SVG badge."""
    color = BADGE_COLORS.get(badge_level, "#9CA3AF")
    label_text = "ThinkNEO Trust Score"
    value_text = f"{score}/100 | {BADGE_LABELS.get(badge_level, 'Unknown')}"

    # Calculate widths based on text length (approximate)
    label_width = len(label_text) * 6.5 + 14
    value_width = len(value_text) * 6.5 + 14
    total_width = label_width + value_width

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{total_width}" height="20" role="img" aria-label="{label_text}: {value_text}">
  <title>{label_text}: {value_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif"
     text-rendering="geometricPrecision" font-size="11">
    <text aria-hidden="true" x="{label_width / 2}" y="15" fill="#010101" fill-opacity=".3">
      {label_text}
    </text>
    <text x="{label_width / 2}" y="14">{label_text}</text>
    <text aria-hidden="true" x="{label_width + value_width / 2}" y="15" fill="#010101" fill-opacity=".3">
      {value_text}
    </text>
    <text x="{label_width + value_width / 2}" y="14">{value_text}</text>
  </g>
</svg>"""
    return svg


def _generate_error_svg(message: str) -> str:
    """Generate an error badge SVG."""
    label_text = "ThinkNEO Trust Score"
    value_text = message
    label_width = len(label_text) * 6.5 + 14
    value_width = len(value_text) * 6.5 + 14
    total_width = label_width + value_width

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img">
  <title>{label_text}: {value_text}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="#E5534B"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif"
     text-rendering="geometricPrecision" font-size="11">
    <text x="{label_width / 2}" y="14">{label_text}</text>
    <text x="{label_width + value_width / 2}" y="14">{value_text}</text>
  </g>
</svg>"""
    return svg


class BadgeMiddleware:
    """
    ASGI middleware that intercepts GET /badge/{token} and /badge/{token}.json
    requests and returns SVG or JSON badge responses.
    All other requests pass through to the inner app.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")

            if method == "GET" and path.startswith("/badge/"):
                match = _BADGE_RE.match(path)
                if match:
                    report_token = match.group(1)
                    is_json = match.group(2) == ".json"

                    # Lazy import to avoid circular dependencies
                    from .tools.trust_score import get_trust_badge_by_token

                    badge_data = get_trust_badge_by_token(report_token)

                    if is_json:
                        if badge_data:
                            response = JSONResponse(
                                {
                                    "org_name": badge_data["org_name"],
                                    "score": badge_data["score"],
                                    "badge_level": badge_data["badge_level"],
                                    "badge_label": BADGE_LABELS.get(badge_data["badge_level"], "Unknown"),
                                    "evaluated_at": badge_data["evaluated_at"].isoformat() if badge_data["evaluated_at"] else None,
                                    "valid_until": badge_data["valid_until"].isoformat() if badge_data["valid_until"] else None,
                                },
                                status_code=200,
                                headers={
                                    "Cache-Control": "public, max-age=3600",
                                    "Access-Control-Allow-Origin": "*",
                                },
                            )
                        else:
                            response = JSONResponse(
                                {"error": "not_found", "message": "Badge not found or expired"},
                                status_code=404,
                                headers={"Access-Control-Allow-Origin": "*"},
                            )
                        await response(scope, receive, send)
                        return
                    else:
                        # Return SVG
                        if badge_data:
                            svg = _generate_svg(
                                badge_data["score"],
                                badge_data["badge_level"],
                                badge_data["org_name"],
                            )
                            response = Response(
                                content=svg,
                                status_code=200,
                                media_type="image/svg+xml",
                                headers={
                                    "Cache-Control": "public, max-age=3600",
                                    "Access-Control-Allow-Origin": "*",
                                },
                            )
                        else:
                            svg = _generate_error_svg("not found")
                            response = Response(
                                content=svg,
                                status_code=404,
                                media_type="image/svg+xml",
                                headers={"Access-Control-Allow-Origin": "*"},
                            )
                        await response(scope, receive, send)
                        return

        await self.app(scope, receive, send)
