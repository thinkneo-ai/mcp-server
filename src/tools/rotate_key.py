"""
Tool: thinkneo_rotate_key
Rotate an API key — generate new, keep same tier/limits, revoke old.
Authenticated tool — the key being rotated must be the one used to call this.

Critical enterprise feature: keys should never be static forever. This enables
automated rotation in CI/CD without manual intervention.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import get_bearer_token
from ..plans import require_plan
from ..database import _get_conn, hash_key
from ._common import utcnow

logger = logging.getLogger(__name__)


def _generate_key() -> str:
    """Generate a new ThinkNEO API key: tnk_<40 hex chars>."""
    return "tnk_" + secrets.token_hex(20)


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_rotate_key",
        description=(
            "Rotate the current API key. Generates a new key with the same tier and "
            "monthly limit, revokes the old one with reason 'rotated'. "
            "IMPORTANT: the returned new_key is shown ONCE. Store it securely. "
            "The old key will continue to work for a 5-minute grace period to avoid downtime."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False),
    )
    def thinkneo_rotate_key(
        confirm: Annotated[bool, Field(description="Must be true to confirm rotation intent")],
    ) -> str:
        """Rotate the current API key. Generates a new key with the same tier and monthly limit, revokes the old one with reason 'rotated'. IMPORTANT: the returned new_key is shown ONCE. Store it securely."""
        # Require auth — caller must be the key being rotated
        try:
            require_plan("pro")
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, indent=2)

        if not confirm:
            return json.dumps({
                "error": "confirm parameter must be true",
                "message": "Call thinkneo_rotate_key with confirm=true to proceed.",
            }, indent=2)

        old_token = get_bearer_token()
        if not old_token:
            return json.dumps({"error": "No bearer token in request"}, indent=2)

        old_hash = hash_key(old_token)
        new_key = _generate_key()
        new_hash = hash_key(new_key)
        new_prefix = new_key[:8]

        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    # Look up the current key
                    cur.execute(
                        "SELECT email, tier, monthly_limit, scopes, ip_allowlist, rate_limit_per_min FROM api_keys WHERE key_hash = %s",
                        (old_hash,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return json.dumps({
                            "error": "Current key not found in database",
                            "hint": "This tool works with auto-provisioned or enterprise keys only.",
                        }, indent=2)

                    email = row.get("email")
                    tier = row.get("tier", "free")
                    monthly_limit = row.get("monthly_limit", 500)
                    # Pull optional columns if they exist (added in migration)
                    scopes = row.get("scopes")
                    ip_allowlist = row.get("ip_allowlist")
                    rate_limit = row.get("rate_limit_per_min", 60)

                    # Insert the new key
                    cur.execute(
                        """
                        INSERT INTO api_keys (key_hash, key_prefix, email, tier, monthly_limit, plan, scopes, ip_allowlist, rate_limit_per_min, last_rotated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (new_hash, new_prefix, email, tier, monthly_limit, tier, scopes, ip_allowlist, rate_limit),
                    )

                    # Mark old key as rotated (revoked with grace period info in reason)
                    cur.execute(
                        """
                        INSERT INTO revoked_keys (key_hash, key_prefix, reason)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (key_hash) DO NOTHING
                        """,
                        (old_hash, old_token[:8], f"rotated → {new_prefix} at {utcnow()}"),
                    )

            logger.info("Key rotated: %s... → %s", old_token[:8], new_prefix)
            return json.dumps({
                "rotated": True,
                "new_key": new_key,
                "new_key_prefix": new_prefix,
                "old_key_prefix": old_token[:8],
                "tier": tier,
                "monthly_limit": monthly_limit,
                "grace_period_minutes": 5,
                "warning": (
                    "SAVE THE new_key NOW — it will not be shown again. "
                    "Update your applications and secret stores. "
                    "Old key will stop working after the grace period."
                ),
                "rotated_at": utcnow(),
            }, indent=2)
        except Exception as exc:
            logger.error("Key rotation failed: %s", exc)
            return json.dumps({
                "rotated": False,
                "error": str(exc),
            }, indent=2)
