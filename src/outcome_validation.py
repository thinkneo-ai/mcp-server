"""
Outcome Validation Engine — "From Prompt to Proof"

Closes the loop between AI agent actions and real-world outcomes.
An agent claims it performed an action; this engine verifies it actually happened.

Verification adapters:
  - http_status: GET/HEAD a URL and check response code
  - file_exists: Check if a file exists (+ optional hash)
  - db_row_exists: Check if a database row exists via count query
  - webhook: Wait for external callback confirmation
  - manual: Flag for human review
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Table bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _ensure_tables(conn) -> None:
    """Create outcome_claims table if it doesn't exist (idempotent)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'outcome_claims'
            )
        """)
        if not cur.fetchone()["exists"]:
            migration_path = "/app/migrations/005_outcome_validation.sql"
            import pathlib
            sql_path = pathlib.Path(migration_path)
            if not sql_path.exists():
                sql_path = pathlib.Path("/opt/thinkneo-mcp-server/migrations/005_outcome_validation.sql")
            if sql_path.exists():
                cur.execute(sql_path.read_text())
                logger.info("Outcome validation tables created from migration file")
            else:
                logger.warning("Migration file not found — tables must be created manually")


_tables_checked = False


def _check_tables() -> None:
    global _tables_checked
    if _tables_checked:
        return
    try:
        with _get_conn() as conn:
            _ensure_tables(conn)
        _tables_checked = True
    except Exception as exc:
        logger.warning("Table check failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Claim registration
# ---------------------------------------------------------------------------

def register_claim(
    api_key: str,
    action: str,
    target: str,
    evidence_type: str,
    agent_name: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ttl_hours: int = 24,
) -> Dict[str, Any]:
    """
    Register an action claim from an agent.
    Returns claim_id for tracking and later verification.
    """
    _check_tables()
    key_h = hash_key(api_key)

    valid_actions = {
        "email_sent", "http_request", "file_written", "db_insert",
        "pr_created", "payment_processed", "message_sent", "api_call",
        "task_completed", "data_exported", "notification_sent", "custom",
    }
    if action not in valid_actions:
        action = "custom"

    valid_evidence = {
        "http_status", "smtp_delivery", "db_row_exists",
        "file_exists", "webhook", "manual",
    }
    if evidence_type not in valid_evidence:
        raise ValueError(
            f"Invalid evidence_type '{evidence_type}'. "
            f"Must be one of: {sorted(valid_evidence)}"
        )

    claim_id = str(uuid.uuid4())
    meta = metadata or {}
    expires = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outcome_claims
                        (claim_id, session_id, api_key_hash, agent_name,
                         action, target, evidence_type, claim_metadata, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING claim_id, claimed_at
                    """,
                    (
                        claim_id, session_id, key_h, agent_name,
                        action, target, evidence_type,
                        _json_dumps(meta), expires,
                    ),
                )
                row = cur.fetchone()
                return {
                    "claim_id": str(row["claim_id"]),
                    "status": "pending",
                    "action": action,
                    "target": target,
                    "evidence_type": evidence_type,
                    "claimed_at": row["claimed_at"].isoformat(),
                    "expires_at": expires.isoformat(),
                    "verification_url": f"https://mcp.thinkneo.ai/claims/{claim_id}",
                }
    except Exception as exc:
        logger.error("register_claim failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Verification engine
# ---------------------------------------------------------------------------

def verify_claim(
    api_key: str,
    claim_id: str,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Attempt to verify a claim using the appropriate adapter.
    Returns verification result with evidence.
    """
    _check_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM outcome_claims
                    WHERE claim_id = %s AND api_key_hash = %s
                    """,
                    (claim_id, key_h),
                )
                claim = cur.fetchone()

                if not claim:
                    raise ValueError(f"Claim {claim_id} not found")

                # Already verified or failed (unless force)
                if claim["status"] in ("verified", "failed") and not force:
                    return _format_claim(claim)

                # Check expiry
                now = datetime.now(timezone.utc)
                if claim["expires_at"] and now > claim["expires_at"]:
                    cur.execute(
                        """
                        UPDATE outcome_claims
                        SET status = 'expired'
                        WHERE claim_id = %s
                        """,
                        (claim_id,),
                    )
                    claim = dict(claim)
                    claim["status"] = "expired"
                    return _format_claim(claim)

                # Mark as verifying
                cur.execute(
                    "UPDATE outcome_claims SET status = 'verifying' WHERE claim_id = %s",
                    (claim_id,),
                )

                # Run the appropriate verification adapter
                evidence_type = claim["evidence_type"]
                target = claim["target"]
                meta = claim["claim_metadata"] or {}

                adapter_result = _run_adapter(evidence_type, target, meta)

                # Update claim with result
                new_status = "verified" if adapter_result["success"] else "failed"
                failure_reason = adapter_result.get("reason") if not adapter_result["success"] else None

                cur.execute(
                    """
                    UPDATE outcome_claims
                    SET status = %s,
                        verified_at = CASE WHEN %s = 'verified' THEN NOW() ELSE verified_at END,
                        evidence = %s::jsonb,
                        verifier = %s,
                        failure_reason = %s,
                        retry_count = retry_count + 1
                    WHERE claim_id = %s
                    RETURNING *
                    """,
                    (
                        new_status, new_status,
                        _json_dumps(adapter_result["evidence"]),
                        adapter_result["verifier"],
                        failure_reason,
                        claim_id,
                    ),
                )
                updated = cur.fetchone()
                return _format_claim(updated)

    except ValueError:
        raise
    except Exception as exc:
        logger.error("verify_claim failed: %s", exc)
        raise


def _run_adapter(
    evidence_type: str,
    target: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run the appropriate verification adapter.
    Returns {success: bool, evidence: dict, verifier: str, reason?: str}
    """
    adapters = {
        "http_status": _verify_http_status,
        "file_exists": _verify_file_exists,
        "db_row_exists": _verify_db_row_exists,
        "webhook": _verify_webhook,
        "smtp_delivery": _verify_smtp_placeholder,
        "manual": _verify_manual,
    }

    adapter_fn = adapters.get(evidence_type)
    if not adapter_fn:
        return {
            "success": False,
            "evidence": {"error": f"No adapter for evidence_type: {evidence_type}"},
            "verifier": "none",
            "reason": f"Unsupported evidence type: {evidence_type}",
        }

    try:
        return adapter_fn(target, metadata)
    except Exception as exc:
        return {
            "success": False,
            "evidence": {"error": str(exc)},
            "verifier": f"{evidence_type}_adapter",
            "reason": f"Adapter error: {str(exc)}",
        }


# ---------------------------------------------------------------------------
# Verification adapters
# ---------------------------------------------------------------------------

def _verify_http_status(target: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify by checking HTTP status of a URL.
    Expects target = URL, metadata may include expected_status (default 200).
    """
    expected_status = metadata.get("expected_status", 200)
    method = metadata.get("method", "HEAD").upper()
    timeout = min(metadata.get("timeout_seconds", 10), 30)

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            if method == "HEAD":
                resp = client.head(target)
            else:
                resp = client.get(target)

            success = resp.status_code == expected_status
            return {
                "success": success,
                "evidence": {
                    "url": target,
                    "method": method,
                    "status_code": resp.status_code,
                    "expected_status": expected_status,
                    "content_type": resp.headers.get("content-type", ""),
                    "content_length": resp.headers.get("content-length", ""),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
                "verifier": "http_adapter",
                "reason": None if success else f"Expected status {expected_status}, got {resp.status_code}",
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "evidence": {"url": target, "error": "timeout"},
            "verifier": "http_adapter",
            "reason": f"HTTP request timed out after {timeout}s",
        }
    except Exception as exc:
        return {
            "success": False,
            "evidence": {"url": target, "error": str(exc)},
            "verifier": "http_adapter",
            "reason": f"HTTP request failed: {exc}",
        }


def _verify_file_exists(target: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that a file exists at the given path.
    Optionally checks file hash if expected_hash is provided.
    """
    import os
    import stat

    # Security: restrict to safe paths
    allowed_prefixes = ("/opt/", "/tmp/", "/home/openclaw/")
    if not any(target.startswith(p) for p in allowed_prefixes):
        return {
            "success": False,
            "evidence": {"path": target, "error": "path_not_allowed"},
            "verifier": "file_adapter",
            "reason": f"Path must start with one of: {allowed_prefixes}",
        }

    exists = os.path.exists(target)
    evidence: Dict[str, Any] = {
        "path": target,
        "exists": exists,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if exists:
        try:
            st = os.stat(target)
            evidence["size_bytes"] = st.st_size
            evidence["modified_at"] = datetime.fromtimestamp(
                st.st_mtime, tz=timezone.utc
            ).isoformat()
            evidence["is_file"] = stat.S_ISREG(st.st_mode)

            # Optional hash verification
            expected_hash = metadata.get("expected_hash")
            if expected_hash and stat.S_ISREG(st.st_mode):
                sha256 = hashlib.sha256()
                with open(target, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256.update(chunk)
                actual_hash = sha256.hexdigest()
                evidence["sha256"] = actual_hash
                if actual_hash != expected_hash:
                    return {
                        "success": False,
                        "evidence": evidence,
                        "verifier": "file_adapter",
                        "reason": f"Hash mismatch: expected {expected_hash[:16]}..., got {actual_hash[:16]}...",
                    }
        except OSError as exc:
            evidence["stat_error"] = str(exc)

    return {
        "success": exists,
        "evidence": evidence,
        "verifier": "file_adapter",
        "reason": None if exists else f"File not found: {target}",
    }


def _verify_db_row_exists(target: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that a database row exists.
    Target = table_name, metadata must include 'where' conditions.
    Security: only queries the thinkneo_mcp database with parameterized queries.
    """
    # Only allow querying specific safe tables
    safe_tables = {
        "usage_log", "api_keys", "agent_sessions", "agent_events",
        "outcome_claims", "router_requests", "trust_scores",
        "mcp_registry", "verification_stats_daily",
    }

    table = target
    if table not in safe_tables:
        return {
            "success": False,
            "evidence": {"table": table, "error": "table_not_allowed"},
            "verifier": "db_adapter",
            "reason": f"Table must be one of: {sorted(safe_tables)}",
        }

    where_col = metadata.get("where_column")
    where_val = metadata.get("where_value")

    if not where_col or not where_val:
        return {
            "success": False,
            "evidence": {"error": "missing_where_conditions"},
            "verifier": "db_adapter",
            "reason": "metadata must include 'where_column' and 'where_value'",
        }

    # Sanitize column name (alphanumeric + underscore only)
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', where_col):
        return {
            "success": False,
            "evidence": {"error": "invalid_column_name"},
            "verifier": "db_adapter",
            "reason": f"Invalid column name: {where_col}",
        }

    try:
        from psycopg import sql
        with _get_conn() as conn:
            with conn.cursor() as cur:
                query = sql.SQL("SELECT COUNT(*) AS cnt FROM {} WHERE {} = %s").format(
                    sql.Identifier(table),
                    sql.Identifier(where_col),
                )
                cur.execute(query, (where_val,))
                row = cur.fetchone()
                count = row["cnt"]
                success = count > 0

                return {
                    "success": success,
                    "evidence": {
                        "table": table,
                        "where": {where_col: where_val},
                        "row_count": count,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "verifier": "db_adapter",
                    "reason": None if success else f"No rows found in {table} where {where_col} = {where_val}",
                }
    except Exception as exc:
        return {
            "success": False,
            "evidence": {"error": str(exc)},
            "verifier": "db_adapter",
            "reason": f"Database query failed: {exc}",
        }


def _verify_webhook(target: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Webhook verification: check if a webhook callback was received.
    For now, returns pending status — full implementation requires a webhook receiver.
    """
    return {
        "success": False,
        "evidence": {
            "webhook_url": target,
            "status": "awaiting_callback",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        },
        "verifier": "webhook_adapter",
        "reason": "Webhook callback not yet received. Retry later.",
    }


def _verify_smtp_placeholder(target: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    SMTP delivery verification placeholder.
    Full implementation requires access to SMTP logs or delivery status notifications.
    """
    return {
        "success": False,
        "evidence": {
            "recipient": target,
            "status": "delivery_check_not_available",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "SMTP delivery verification requires mailserver DSN integration. Use manual verification for now.",
        },
        "verifier": "smtp_adapter",
        "reason": "SMTP delivery verification not yet configured. Use evidence_type 'manual' as alternative.",
    }


def _verify_manual(target: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Manual verification: flags the claim for human review.
    Cannot auto-verify — always returns pending.
    """
    return {
        "success": False,
        "evidence": {
            "target": target,
            "status": "requires_human_review",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "review_url": f"https://mcp.thinkneo.ai/claims/review",
        },
        "verifier": "manual_adapter",
        "reason": "Claim requires manual human verification.",
    }


# ---------------------------------------------------------------------------
# Proof retrieval
# ---------------------------------------------------------------------------

def get_proof(api_key: str, claim_id: str) -> Dict[str, Any]:
    """Retrieve the full proof record for a claim."""
    _check_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM outcome_claims
                    WHERE claim_id = %s AND api_key_hash = %s
                    """,
                    (claim_id, key_h),
                )
                claim = cur.fetchone()
                if not claim:
                    raise ValueError(f"Claim {claim_id} not found")

                result = _format_claim(claim)

                # If verified, add proof integrity hash
                if claim["status"] == "verified" and claim["evidence"]:
                    proof_data = {
                        "claim_id": str(claim["claim_id"]),
                        "action": claim["action"],
                        "target": claim["target"],
                        "verified_at": claim["verified_at"].isoformat() if claim["verified_at"] else None,
                        "evidence": claim["evidence"],
                    }
                    proof_hash = hashlib.sha256(
                        json.dumps(proof_data, sort_keys=True, default=str).encode()
                    ).hexdigest()
                    result["proof_hash"] = proof_hash
                    result["proof_integrity"] = "sha256"
                    result["tamper_evident"] = True

                return result
    except ValueError:
        raise
    except Exception as exc:
        logger.error("get_proof failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Verification dashboard
# ---------------------------------------------------------------------------

def get_verification_dashboard(
    api_key: str,
    period: str = "7d",
) -> Dict[str, Any]:
    """
    Aggregated verification metrics for the given period.
    Returns rates, trends, top actions, failure patterns.
    """
    _check_tables()
    key_h = hash_key(api_key)

    period_map = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = period_map.get(period, timedelta(days=7))
    since = datetime.now(timezone.utc) - delta

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Overall stats
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS total_claims,
                        COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                        COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                        COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                        COUNT(*) FILTER (WHERE status = 'expired') AS expired,
                        COUNT(*) FILTER (WHERE status = 'skipped') AS skipped
                    FROM outcome_claims
                    WHERE api_key_hash = %s AND claimed_at >= %s
                    """,
                    (key_h, since),
                )
                stats = cur.fetchone()

                total = stats["total_claims"]
                verified = stats["verified"]
                failed = stats["failed"]
                decidable = verified + failed

                verification_rate = round(
                    (verified / decidable * 100) if decidable > 0 else 0, 2
                )

                # Average verification time (for verified claims)
                cur.execute(
                    """
                    SELECT COALESCE(
                        AVG(EXTRACT(EPOCH FROM (verified_at - claimed_at)) * 1000),
                        0
                    ) AS avg_ms
                    FROM outcome_claims
                    WHERE api_key_hash = %s AND claimed_at >= %s AND status = 'verified'
                    """,
                    (key_h, since),
                )
                avg_row = cur.fetchone()
                avg_verification_ms = round(float(avg_row["avg_ms"]), 0)

                # Top actions
                cur.execute(
                    """
                    SELECT action, COUNT(*) AS cnt,
                           COUNT(*) FILTER (WHERE status = 'verified') AS verified_cnt,
                           COUNT(*) FILTER (WHERE status = 'failed') AS failed_cnt
                    FROM outcome_claims
                    WHERE api_key_hash = %s AND claimed_at >= %s
                    GROUP BY action
                    ORDER BY cnt DESC
                    LIMIT 10
                    """,
                    (key_h, since),
                )
                top_actions = [
                    {
                        "action": r["action"],
                        "total": r["cnt"],
                        "verified": r["verified_cnt"],
                        "failed": r["failed_cnt"],
                        "rate": round(
                            r["verified_cnt"] / (r["verified_cnt"] + r["failed_cnt"]) * 100
                            if (r["verified_cnt"] + r["failed_cnt"]) > 0 else 0,
                            1,
                        ),
                    }
                    for r in cur.fetchall()
                ]

                # Top failure reasons
                cur.execute(
                    """
                    SELECT failure_reason, COUNT(*) AS cnt
                    FROM outcome_claims
                    WHERE api_key_hash = %s AND claimed_at >= %s
                      AND status = 'failed' AND failure_reason IS NOT NULL
                    GROUP BY failure_reason
                    ORDER BY cnt DESC
                    LIMIT 5
                    """,
                    (key_h, since),
                )
                top_failures = [
                    {"reason": r["failure_reason"], "count": r["cnt"]}
                    for r in cur.fetchall()
                ]

                # Daily trend
                cur.execute(
                    """
                    SELECT
                        DATE(claimed_at) AS day,
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                        COUNT(*) FILTER (WHERE status = 'failed') AS failed
                    FROM outcome_claims
                    WHERE api_key_hash = %s AND claimed_at >= %s
                    GROUP BY DATE(claimed_at)
                    ORDER BY day ASC
                    """,
                    (key_h, since),
                )
                daily_trend = [
                    {
                        "date": r["day"].isoformat(),
                        "total": r["total"],
                        "verified": r["verified"],
                        "failed": r["failed"],
                        "rate": round(
                            r["verified"] / (r["verified"] + r["failed"]) * 100
                            if (r["verified"] + r["failed"]) > 0 else 0,
                            1,
                        ),
                    }
                    for r in cur.fetchall()
                ]

                # Agent reliability ranking
                cur.execute(
                    """
                    SELECT agent_name, COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE status = 'verified') AS verified
                    FROM outcome_claims
                    WHERE api_key_hash = %s AND claimed_at >= %s
                      AND agent_name IS NOT NULL
                    GROUP BY agent_name
                    ORDER BY total DESC
                    LIMIT 10
                    """,
                    (key_h, since),
                )
                agent_reliability = [
                    {
                        "agent": r["agent_name"],
                        "total_claims": r["total"],
                        "verified": r["verified"],
                        "reliability_pct": round(
                            r["verified"] / r["total"] * 100 if r["total"] > 0 else 0,
                            1,
                        ),
                    }
                    for r in cur.fetchall()
                ]

                return {
                    "period": period,
                    "since": since.isoformat(),
                    "total_claims": total,
                    "verified": verified,
                    "failed": failed,
                    "pending": stats["pending"],
                    "expired": stats["expired"],
                    "verification_rate_pct": verification_rate,
                    "avg_verification_time_ms": avg_verification_ms,
                    "top_actions": top_actions,
                    "top_failure_reasons": top_failures,
                    "agent_reliability": agent_reliability,
                    "daily_trend": daily_trend,
                    "dashboard_url": "https://mcp.thinkneo.ai/verification",
                }
    except Exception as exc:
        logger.error("get_verification_dashboard failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

def expire_stale_claims() -> int:
    """Mark expired claims. Returns count of expired claims."""
    _check_tables()
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE outcome_claims
                    SET status = 'expired'
                    WHERE status IN ('pending', 'verifying')
                      AND expires_at < NOW()
                    """,
                )
                return cur.rowcount
    except Exception as exc:
        logger.warning("expire_stale_claims failed: %s", exc)
        return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_claim(claim) -> Dict[str, Any]:
    """Format a claim row into a clean API response."""
    c = dict(claim) if not isinstance(claim, dict) else claim
    return {
        "claim_id": str(c["claim_id"]),
        "action": c["action"],
        "target": c["target"],
        "evidence_type": c["evidence_type"],
        "status": c["status"],
        "agent_name": c.get("agent_name"),
        "session_id": str(c["session_id"]) if c.get("session_id") else None,
        "claimed_at": c["claimed_at"].isoformat() if hasattr(c["claimed_at"], "isoformat") else c["claimed_at"],
        "verified_at": c["verified_at"].isoformat() if c.get("verified_at") and hasattr(c["verified_at"], "isoformat") else c.get("verified_at"),
        "evidence": c.get("evidence"),
        "verifier": c.get("verifier"),
        "failure_reason": c.get("failure_reason"),
        "retry_count": c.get("retry_count", 0),
        "expires_at": c["expires_at"].isoformat() if hasattr(c["expires_at"], "isoformat") else c["expires_at"],
    }


def _json_dumps(obj: Any) -> str:
    """Safe JSON serialization."""
    return json.dumps(obj, default=str, ensure_ascii=False)
