"""
Tool: thinkneo_schedule_demo
Collects contact info to schedule a demo with the ThinkNEO team.
Public tool — no authentication required.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..config import get_settings
from ._common import utcnow

logger = logging.getLogger(__name__)

_VALID_ROLES = {"cto", "cfo", "security", "engineering", "other"}


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_schedule_demo",
        description=(
            "Schedule a demo or discovery call with the ThinkNEO team. "
            "Collects contact information and preferences. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True),
    )
    def thinkneo_schedule_demo(
        contact_name: Annotated[str, Field(description="Full name of the person requesting the demo")],
        company: Annotated[str, Field(description="Company or organization name")],
        email: Annotated[str, Field(description="Business email address to receive follow-up from the ThinkNEO team")],
        role: Annotated[Optional[str], Field(description="Contact's role: cto, cfo, security, engineering, or other")] = None,
        interest: Annotated[Optional[str], Field(description="Primary area of interest: guardrails, finops, observability, governance, or full platform")] = None,
        preferred_dates: Annotated[Optional[str], Field(description="Preferred meeting dates, times, and timezone (e.g., 'Tuesdays or Thursdays, 9-11am EST')")] = None,
        context: Annotated[Optional[str], Field(description="Additional context such as current AI providers used, request volume, or specific use case")] = None,
    ) -> str:
        """Schedule a demo or discovery call with the ThinkNEO team. Collects contact information and preferences."""
        settings = get_settings()

        # Basic validation
        contact_name = contact_name.strip()[:128]
        company = company.strip()[:128]
        email = email.strip()[:256]

        if not contact_name or not company or not email:
            return json.dumps(
                {
                    "success": False,
                    "error": "contact_name, company, and email are required fields.",
                },
                indent=2,
            )

        if "@" not in email or "." not in email.split("@")[-1]:
            return json.dumps(
                {"success": False, "error": f"Invalid email address: '{email}'"},
                indent=2,
            )

        if role and role.lower() not in _VALID_ROLES:
            role = "other"

        booking = {
            "contact_name": contact_name,
            "company": company,
            "email": email,
            "role": role or "not-specified",
            "interest": (interest or "not-specified")[:256],
            "preferred_dates": (preferred_dates or "flexible")[:256],
            "context": (context or "")[:1024],
            "submitted_at": utcnow(),
            "source": "thinkneo-mcp-server",
        }

        # Attempt to forward to webhook if configured
        webhook_sent = False
        if settings.demo_webhook_url:
            try:
                with httpx.Client(timeout=5.0) as client:
                    resp = client.post(
                        settings.demo_webhook_url,
                        json=booking,
                        headers={"Content-Type": "application/json"},
                    )
                    webhook_sent = resp.is_success
            except Exception as exc:
                logger.warning("Demo webhook failed: %s", exc)

        if not webhook_sent:
            logger.info("Demo request (no webhook): %s", json.dumps(booking))

        return json.dumps(
            {
                "success": True,
                "booking_summary": booking,
                "next_steps": (
                    f"Thank you, {contact_name}! A ThinkNEO team member will reach out "
                    f"to {email} within 1 business day to confirm your demo. "
                    "You can also reach us directly at hello@thinkneo.ai."
                ),
                "booking_link": "https://thinkneo.ai/demo",
                "webhook_notified": webhook_sent,
            },
            indent=2,
        )
