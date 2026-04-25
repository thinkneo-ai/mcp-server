"""
Plan enforcement — gate tools by the calling API key's plan tier.

Plan hierarchy:
    free       (level 0) — default for auto-registered keys
    pro        (level 1) — paid tier; unlocks cost/policy/guardrail tools
    enterprise (level 2) — custom pricing; unlimited + SLA
    master     (level 99) — env-configured master keys, bypass every check

Public helpers:
    require_plan(min_plan)  → assert current request meets the minimum; raises PlanRequiredError otherwise.
    current_plan()           → inspect the caller's plan ("anonymous" if no bearer token).

Errors raised are ValueError subclasses, which FastMCP wraps into a
JSON-RPC-style error response visible to the MCP client.
"""

from __future__ import annotations

from typing import Final

from .auth import get_bearer_token
from .config import get_settings
from .database import _get_conn, hash_key

PLAN_RANK: Final[dict[str, int]] = {
    "free": 0,
    "pro": 1,
    "enterprise": 2,
    "master": 99,
}

UPGRADE_URL: Final[str] = "https://mcp.thinkneo.ai/mcp/signup"
CONTACT_EMAIL: Final[str] = "hello@thinkneo.ai"


class PlanRequiredError(ValueError):
    """Raised when the caller's plan does not meet the required minimum."""

    def __init__(self, required: str, current: str) -> None:
        self.required = required
        self.current = current
        self.code = -32001  # JSON-RPC server error range, surfaced in message
        super().__init__(
            f"This tool requires a {required.capitalize()} plan "
            f"(current: {current}). "
            f"Upgrade at {UPGRADE_URL} or contact {CONTACT_EMAIL} for Enterprise."
        )


class AuthenticationRequiredError(ValueError):
    """Raised when no Bearer token is present at all."""

    def __init__(self) -> None:
        self.code = -32002
        super().__init__(
            "Authentication required. Provide a ThinkNEO API key as a Bearer token: "
            "'Authorization: Bearer <api-key>'. "
            f"Get a free key at {UPGRADE_URL}."
        )


def current_plan() -> str:
    """Return the plan of the current request's bearer token.

    Returns "anonymous" if no token is present.
    """
    token = get_bearer_token()
    if not token:
        return "anonymous"

    # Master keys (env-configured) bypass all plan checks.
    settings = get_settings()
    if token in settings.valid_api_keys:
        return "master"

    # Look up key in DB (NO auto-registration, SEC-01)
    key_h = hash_key(token)
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tier FROM api_keys WHERE key_hash = %s", (key_h,))
                row = cur.fetchone()
                if row:
                    return row.get("plan") or row.get("tier") or "free"
    except Exception:
        pass
    return "free"


def require_plan(min_plan: str) -> str:
    """Assert the caller has at least `min_plan`. Returns the caller's plan on success.

    Raises:
        AuthenticationRequiredError: if no Bearer token is supplied.
        PlanRequiredError: if the caller's plan is below `min_plan`.
    """
    if min_plan not in PLAN_RANK:
        raise ValueError(f"Unknown plan: {min_plan!r}")

    plan = current_plan()
    if plan == "anonymous":
        raise AuthenticationRequiredError()

    if PLAN_RANK.get(plan, 0) < PLAN_RANK[min_plan]:
        raise PlanRequiredError(required=min_plan, current=plan)

    return plan
