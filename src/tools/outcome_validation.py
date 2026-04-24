"""
Tools: Outcome Validation Loop — "From Prompt to Proof"

4 MCP tools for verifying AI agent action claims:
  - thinkneo_register_claim: Agent registers an action it claims to have performed
  - thinkneo_verify_claim: Trigger verification of a registered claim
  - thinkneo_get_proof: Retrieve the immutable proof record
  - thinkneo_verification_dashboard: Aggregated verification metrics
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth, get_bearer_token
from ..outcome_validation import (
    register_claim,
    verify_claim,
    get_proof,
    get_verification_dashboard,
)
from .._common_obs import utcnow_obs


def register(mcp: FastMCP) -> None:

    # ------------------------------------------------------------------
    # 1. thinkneo_register_claim
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_register_claim",
        description=(
            "Register an action claim from an AI agent. The agent declares it performed "
            "an action (e.g., sent an email, created a PR, wrote a file) and ThinkNEO "
            "will verify it actually happened. Returns a claim_id for tracking. "
            "Part of the Outcome Validation Loop — 'From Prompt to Proof'. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_register_claim(
        action: Annotated[str, Field(
            description=(
                "Type of action claimed: 'email_sent', 'http_request', 'file_written', "
                "'db_insert', 'pr_created', 'payment_processed', 'message_sent', "
                "'api_call', 'task_completed', 'data_exported', 'notification_sent', 'custom'"
            )
        )],
        target: Annotated[str, Field(
            description=(
                "Target of the action — what was acted upon. Examples: "
                "'user@example.com' (email), 'https://api.example.com/endpoint' (http), "
                "'/opt/data/report.pdf' (file), 'usage_log' (db table)"
            )
        )],
        evidence_type: Annotated[str, Field(
            description=(
                "How to verify the claim: 'http_status' (check URL response), "
                "'file_exists' (check file path), 'db_row_exists' (check database row), "
                "'webhook' (wait for callback), 'smtp_delivery' (check email delivery), "
                "'manual' (flag for human review)"
            )
        )],
        agent_name: Annotated[Optional[str], Field(
            description="Name of the agent making the claim (e.g., 'marketing-agent')"
        )] = None,
        session_id: Annotated[Optional[str], Field(
            description="Optional observability session_id to link this claim to a trace"
        )] = None,
        metadata: Annotated[Optional[dict], Field(
            description=(
                "Optional verification context. For http_status: {expected_status: 200, method: 'GET'}. "
                "For file_exists: {expected_hash: 'sha256...'}. "
                "For db_row_exists: {where_column: 'id', where_value: '123'}."
            )
        )] = None,
        ttl_hours: Annotated[int, Field(
            description="Hours until claim expires if not verified (default 24, max 168)"
        )] = 24,
    ) -> str:
        token = require_auth()

        meta = _parse_metadata(metadata)
        ttl = min(max(ttl_hours, 1), 168)  # 1h to 7 days

        result = register_claim(
            api_key=token,
            action=action,
            target=target,
            evidence_type=evidence_type,
            agent_name=agent_name,
            session_id=session_id,
            metadata=meta,
            ttl_hours=ttl,
        )
        result["_hint"] = (
            "Claim registered. Use thinkneo_verify_claim with the claim_id to trigger "
            "verification, or it will be verified automatically. Use thinkneo_get_proof "
            "to retrieve the immutable proof record once verified."
        )
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 2. thinkneo_verify_claim
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_verify_claim",
        description=(
            "Trigger verification of a registered action claim. Runs the appropriate "
            "verification adapter (HTTP check, file check, database check, etc.) and "
            "returns the result with evidence. If already verified, returns cached result "
            "(use force=true to re-verify). "
            "Part of the Outcome Validation Loop — 'From Prompt to Proof'. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_verify_claim(
        claim_id: Annotated[str, Field(description="UUID of the claim to verify (from thinkneo_register_claim)")],
        force: Annotated[bool, Field(description="Force re-verification even if already verified/failed")] = False,
    ) -> str:
        token = require_auth()

        result = verify_claim(
            api_key=token,
            claim_id=claim_id,
            force=force,
        )
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 3. thinkneo_get_proof
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_get_proof",
        description=(
            "Retrieve the immutable proof record for a verified claim. Includes the "
            "original claim, verification evidence, verifier identity, and a SHA-256 "
            "proof hash for tamper detection. This is the 'proof' in 'From Prompt to Proof'. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_get_proof(
        claim_id: Annotated[str, Field(description="UUID of the claim to get proof for")],
    ) -> str:
        token = require_auth()

        result = get_proof(api_key=token, claim_id=claim_id)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 4. thinkneo_verification_dashboard
    # ------------------------------------------------------------------
    @mcp.tool(
        name="thinkneo_verification_dashboard",
        description=(
            "Aggregated outcome verification metrics — verification rates, failure patterns, "
            "agent reliability rankings, and daily trends. Shows how reliably your AI agents "
            "are delivering verified outcomes. "
            "'Datadog for AI outcomes'. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_verification_dashboard(
        period: Annotated[str, Field(description="Time period: '24h', '7d', or '30d'")] = "7d",
    ) -> str:
        token = require_auth()

        valid_periods = {"24h", "7d", "30d"}
        if period not in valid_periods:
            period = "7d"

        result = get_verification_dashboard(api_key=token, period=period)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)


def _parse_metadata(metadata) -> dict:
    """Parse metadata from various input formats."""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            return {"raw": metadata}
    return {"raw": str(metadata)}
