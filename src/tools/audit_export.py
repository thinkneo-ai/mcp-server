"""
MCP Tools: thinkneo_audit_export, thinkneo_set_audit_export, thinkneo_audit_export_status

Export audit logs in SIEM-compatible formats with optional HMAC signing.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth, get_bearer_token
from ..database import hash_key, _get_conn
from ..audit.export import export_events, query_audit_events
from ..audit.formatters import FORMATTERS
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_audit_export",
        description=(
            "Export audit events in SIEM-compatible formats: JSON, CEF (ArcSight/QRadar), "
            "LEEF (IBM QRadar native), syslog (RFC 5424), or CSV. "
            "Supports optional HMAC SHA-256 signing for integrity verification. "
            "Filter by period, event type, and workspace. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_audit_export(
        format: Annotated[str, Field(description=f"Output format: {', '.join(sorted(FORMATTERS.keys()))}")] = "json",
        period: Annotated[str, Field(description="Export period: 1d, 7d, 30d, 90d")] = "7d",
        event_types: Annotated[Optional[str], Field(description="Comma-separated event types to filter (e.g., 'tool_call,task_sent')")] = None,
        workspace: Annotated[Optional[str], Field(description="Filter by workspace")] = None,
        limit: Annotated[int, Field(description="Max events to export (1-10000)")] = 1000,
        sign_hmac: Annotated[bool, Field(description="Sign export with HMAC SHA-256 for integrity")] = False,
        hmac_key: Annotated[Optional[str], Field(description="HMAC key for signing (required if sign_hmac=true)")] = None,
    ) -> str:
        """Export audit events in SIEM-compatible formats: JSON, CEF (ArcSight/QRadar), LEEF (IBM QRadar native), syslog (RFC 5424), or CSV. Supports optional HMAC SHA-256 signing for integrity verification."""
        token = require_auth()
        key_h = hash_key(token)

        period_map = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}
        days = period_map.get(period, 7)
        limit = max(1, min(limit, 10000))

        types_filter = [t.strip() for t in event_types.split(",")] if event_types else None

        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    events = query_audit_events(cur, key_h, days, types_filter, workspace, limit)
        except Exception:
            events = []

        result = export_events(events, format, sign_hmac, hmac_key or "")
        result["period"] = period
        result["filters"] = {"event_types": types_filter, "workspace": workspace}
        return json.dumps(result, indent=2, default=str)

    @mcp.tool(
        name="thinkneo_set_audit_export",
        description=(
            "Configure automated audit export to a SIEM integration (Splunk HEC, "
            "Elasticsearch, or generic webhook). Validates endpoint URL for SSRF safety. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_set_audit_export(
        integration: Annotated[str, Field(description="Integration type: splunk, elastic, webhook")],
        endpoint_url: Annotated[str, Field(description="SIEM endpoint URL (e.g., https://splunk.example.com:8088/services/collector)")],
        auth_token: Annotated[Optional[str], Field(description="Auth token for the integration")] = None,
        enabled: Annotated[bool, Field(description="Enable or disable the export")] = True,
    ) -> str:
        """Configure automated audit export to a SIEM integration (Splunk HEC, Elasticsearch, or generic webhook). Validates endpoint URL for SSRF safety."""
        token = require_auth()
        key_h = hash_key(token)

        if integration not in ("splunk", "elastic", "webhook"):
            return json.dumps({"error": f"Invalid integration '{integration}'. Must be: splunk, elastic, webhook"})

        # SSRF protection
        from ..marketplace import _is_safe_url
        safe, reason = _is_safe_url(endpoint_url)
        if not safe:
            return json.dumps({"error": f"Endpoint blocked (SSRF protection): {reason}"})

        # Store config (hash the auth token)
        token_hash = hash_key(auth_token) if auth_token else None

        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO audit_export_configs (api_key_hash, integration, endpoint_url, auth_token_hash, enabled)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (api_key_hash, integration) DO UPDATE SET
                            endpoint_url = EXCLUDED.endpoint_url,
                            auth_token_hash = EXCLUDED.auth_token_hash,
                            enabled = EXCLUDED.enabled,
                            updated_at = NOW()
                        RETURNING id
                    """, (key_h, integration, endpoint_url, token_hash, enabled))
                    row = cur.fetchone()
                    config_id = row["id"] if row else None
        except Exception as e:
            return json.dumps({"error": f"Failed to save config: {str(e)[:100]}"})

        return json.dumps({
            "status": "configured",
            "integration": integration,
            "endpoint": endpoint_url,
            "enabled": enabled,
            "config_id": config_id,
            "configured_at": utcnow(),
        }, indent=2)

    @mcp.tool(
        name="thinkneo_audit_export_status",
        description=(
            "View configured audit export integrations and their last export results. "
            "Shows integration type, endpoint, enabled status, and recent export history. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_audit_export_status() -> str:
        """View configured audit export integrations and their last export results. Shows integration type, endpoint, enabled status, and recent export history."""
        token = require_auth()
        key_h = hash_key(token)

        configs = []
        try:
            with _get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, integration, endpoint_url, enabled, created_at, updated_at
                        FROM audit_export_configs
                        WHERE api_key_hash = %s
                        ORDER BY created_at DESC
                    """, (key_h,))
                    configs = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

        return json.dumps({
            "configs": configs,
            "total": len(configs),
            "fetched_at": utcnow(),
        }, indent=2, default=str)
