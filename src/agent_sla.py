"""
Agent SLA — Outcome Service Level Agreements

SLAs for AI agents: accuracy, quality, cost efficiency, safety, latency.
Monitors actual metrics, detects breaches, triggers actions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)

_tables_checked = False


def _ensure_tables() -> None:
    global _tables_checked
    if _tables_checked:
        return
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_slas')")
                if not cur.fetchone()["exists"]:
                    import pathlib
                    for p in ["/app/migrations/009_agent_sla.sql",
                              "/opt/thinkneo-mcp-server/migrations/009_agent_sla.sql"]:
                        path = pathlib.Path(p)
                        if path.exists():
                            cur.execute(path.read_text())
                            logger.info("Agent SLA tables created")
                            break
        _tables_checked = True
    except Exception as exc:
        logger.warning("SLA table check failed: %s", exc)


VALID_METRICS = {"accuracy", "response_quality", "cost_efficiency", "safety", "latency"}
VALID_ACTIONS = {"alert", "escalate", "disable", "switch_model"}
VALID_WINDOWS = {"1h", "24h", "7d", "30d"}

WINDOW_MAP = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


# ---------------------------------------------------------------------------
# SLA CRUD
# ---------------------------------------------------------------------------

def define_sla(
    api_key: str,
    agent_name: str,
    metric: str,
    threshold: float,
    window: str = "7d",
    breach_action: str = "alert",
    threshold_direction: str = "min",
) -> Dict[str, Any]:
    """Define or update an SLA for an agent."""
    _ensure_tables()
    key_h = hash_key(api_key)

    if metric not in VALID_METRICS:
        raise ValueError(f"Invalid metric. Must be one of: {sorted(VALID_METRICS)}")
    if breach_action not in VALID_ACTIONS:
        raise ValueError(f"Invalid breach_action. Must be one of: {sorted(VALID_ACTIONS)}")
    if window not in VALID_WINDOWS:
        raise ValueError(f"Invalid window. Must be one of: {sorted(VALID_WINDOWS)}")

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_slas
                        (api_key_hash, agent_name, metric, threshold, threshold_direction,
                         sla_window, breach_action)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (api_key_hash, agent_name, metric)
                    DO UPDATE SET
                        threshold = EXCLUDED.threshold,
                        threshold_direction = EXCLUDED.threshold_direction,
                        sla_window = EXCLUDED.sla_window,
                        breach_action = EXCLUDED.breach_action,
                        enabled = TRUE,
                        updated_at = NOW()
                    RETURNING sla_id, created_at
                    """,
                    (key_h, agent_name, metric, threshold, threshold_direction,
                     window, breach_action),
                )
                row = cur.fetchone()
                return {
                    "sla_id": str(row["sla_id"]),
                    "agent_name": agent_name,
                    "metric": metric,
                    "threshold": threshold,
                    "threshold_direction": threshold_direction,
                    "window": window,
                    "breach_action": breach_action,
                    "created_at": row["created_at"].isoformat(),
                }
    except ValueError:
        raise
    except Exception as exc:
        logger.error("define_sla failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# SLA Status / Evaluation
# ---------------------------------------------------------------------------

def get_sla_status(api_key: str, agent_name: Optional[str] = None) -> Dict[str, Any]:
    """Evaluate current SLA status for all agents or a specific agent."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                where = "api_key_hash = %s AND enabled = TRUE"
                params = [key_h]
                if agent_name:
                    where += " AND agent_name = %s"
                    params.append(agent_name)

                cur.execute(f"SELECT * FROM agent_slas WHERE {where} ORDER BY agent_name, metric", params)
                slas = cur.fetchall()

                results = []
                for sla in slas:
                    actual = _evaluate_metric(cur, key_h, sla["agent_name"], sla["metric"], sla["sla_window"])
                    threshold = float(sla["threshold"])
                    direction = sla["threshold_direction"]

                    if direction == "min":
                        healthy = actual >= threshold
                    else:
                        healthy = actual <= threshold

                    status = "healthy" if healthy else "breached"

                    # Check breach
                    if not healthy:
                        _record_breach(cur, sla, actual)

                    # Error budget
                    if direction == "min" and threshold > 0:
                        error_budget = max(0, actual - threshold)
                        error_budget_pct = round(error_budget / threshold * 100, 1)
                    else:
                        error_budget = None
                        error_budget_pct = None

                    results.append({
                        "sla_id": str(sla["sla_id"]),
                        "agent_name": sla["agent_name"],
                        "metric": sla["metric"],
                        "threshold": threshold,
                        "threshold_direction": direction,
                        "actual_value": actual,
                        "window": sla["sla_window"],
                        "status": status,
                        "breach_action": sla["breach_action"],
                        "error_budget_remaining_pct": error_budget_pct,
                    })

                healthy_count = sum(1 for r in results if r["status"] == "healthy")
                breached_count = sum(1 for r in results if r["status"] == "breached")

                return {
                    "total_slas": len(results),
                    "healthy": healthy_count,
                    "breached": breached_count,
                    "overall_status": "healthy" if breached_count == 0 else "breached",
                    "slas": results,
                }

    except Exception as exc:
        logger.error("get_sla_status failed: %s", exc)
        raise


def _evaluate_metric(cur, key_h: str, agent_name: str, metric: str, window: str) -> float:
    """Calculate the actual metric value for an agent."""
    delta = WINDOW_MAP.get(window, timedelta(days=7))
    since = datetime.now(timezone.utc) - delta

    if metric == "accuracy":
        # From outcome_claims: verified / (verified + failed) * 100
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM outcome_claims
                WHERE api_key_hash = %s AND agent_name = %s AND claimed_at >= %s
                """,
                (key_h, agent_name, since),
            )
            row = cur.fetchone()
            decidable = row["verified"] + row["failed"]
            return round(row["verified"] / decidable * 100 if decidable > 0 else 100, 2)
        except Exception:
            return 100.0

    elif metric == "safety":
        # From guardrail evaluations: pass rate
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE event_type = 'guardrail_triggered') AS triggered
                FROM agent_events e
                JOIN agent_sessions s ON e.session_id = s.session_id
                WHERE s.api_key_hash = %s AND s.agent_name = %s AND e.timestamp >= %s
                """,
                (key_h, agent_name, since),
            )
            row = cur.fetchone()
            total = row["total"]
            if total == 0:
                return 100.0
            return round((1 - row["triggered"] / total) * 100, 2)
        except Exception:
            return 100.0

    elif metric == "latency":
        # Average latency from agent_events
        try:
            cur.execute(
                """
                SELECT COALESCE(AVG(e.latency_ms), 0) AS avg_lat
                FROM agent_events e
                JOIN agent_sessions s ON e.session_id = s.session_id
                WHERE s.api_key_hash = %s AND s.agent_name = %s AND e.timestamp >= %s
                  AND e.latency_ms > 0
                """,
                (key_h, agent_name, since),
            )
            return round(float(cur.fetchone()["avg_lat"]), 0)
        except Exception:
            return 0.0

    elif metric == "cost_efficiency":
        # Cost per verified outcome
        try:
            cur.execute(
                """
                SELECT COALESCE(SUM(s.total_cost), 0) AS total_cost
                FROM agent_sessions s
                WHERE s.api_key_hash = %s AND s.agent_name = %s AND s.started_at >= %s
                """,
                (key_h, agent_name, since),
            )
            cost = float(cur.fetchone()["total_cost"])

            cur.execute(
                """
                SELECT COUNT(*) AS cnt FROM outcome_claims
                WHERE api_key_hash = %s AND agent_name = %s AND status = 'verified' AND claimed_at >= %s
                """,
                (key_h, agent_name, since),
            )
            verified = cur.fetchone()["cnt"]
            if verified > 0:
                return round(cost / verified, 4)
            return cost if cost > 0 else 0.0
        except Exception:
            return 0.0

    elif metric == "response_quality":
        # From outcome_benchmarks or feedback
        try:
            cur.execute(
                """
                SELECT COALESCE(AVG(quality_score), 0) AS avg_q
                FROM outcome_feedback
                WHERE api_key_hash = %s AND recorded_at >= %s
                """,
                (key_h, since),
            )
            return round(float(cur.fetchone()["avg_q"]), 2)
        except Exception:
            return 0.0

    return 0.0


def _record_breach(cur, sla, actual_value: float) -> None:
    """Record an SLA breach."""
    try:
        # Check if already breached in the last hour (avoid duplicates)
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM sla_breaches
            WHERE sla_id = %s AND breached_at >= NOW() - INTERVAL '1 hour'
            """,
            (sla["sla_id"],),
        )
        if cur.fetchone()["cnt"] > 0:
            return

        cur.execute(
            """
            INSERT INTO sla_breaches
                (sla_id, api_key_hash, agent_name, metric, threshold, actual_value, breach_action)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                sla["sla_id"], sla["api_key_hash"], sla["agent_name"],
                sla["metric"], sla["threshold"], actual_value, sla["breach_action"],
            ),
        )
        logger.warning("SLA BREACH: %s/%s — %s: actual=%s, threshold=%s",
                        sla["agent_name"], sla["metric"], sla["breach_action"],
                        actual_value, sla["threshold"])
    except Exception as exc:
        logger.warning("_record_breach failed: %s", exc)


# ---------------------------------------------------------------------------
# Breach history
# ---------------------------------------------------------------------------

def get_breaches(api_key: str, days: int = 30, agent_name: Optional[str] = None) -> Dict[str, Any]:
    """Get SLA breach history."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                where = "api_key_hash = %s AND breached_at >= NOW() - INTERVAL '%s days'"
                params = [key_h, days]
                if agent_name:
                    where += " AND agent_name = %s"
                    params.append(agent_name)

                cur.execute(
                    f"""
                    SELECT * FROM sla_breaches
                    WHERE {where}
                    ORDER BY breached_at DESC
                    LIMIT 100
                    """,
                    params,
                )
                breaches = []
                for r in cur.fetchall():
                    breaches.append({
                        "breach_id": str(r["breach_id"]),
                        "agent_name": r["agent_name"],
                        "metric": r["metric"],
                        "threshold": float(r["threshold"]),
                        "actual_value": float(r["actual_value"]),
                        "breach_action": r["breach_action"],
                        "action_taken": r["action_taken"],
                        "resolved": r["resolved_at"] is not None,
                        "breached_at": r["breached_at"].isoformat(),
                    })

                return {
                    "period_days": days,
                    "total_breaches": len(breaches),
                    "unresolved": sum(1 for b in breaches if not b["resolved"]),
                    "breaches": breaches,
                }
    except Exception as exc:
        logger.error("get_breaches failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def get_sla_dashboard(api_key: str) -> Dict[str, Any]:
    """Overview dashboard with all SLAs, current status, and recent breaches."""
    _ensure_tables()
    key_h = hash_key(api_key)

    status = get_sla_status(api_key)
    breaches = get_breaches(api_key, days=7)

    # Agent summary
    agents = {}
    for sla in status.get("slas", []):
        name = sla["agent_name"]
        if name not in agents:
            agents[name] = {"total_slas": 0, "healthy": 0, "breached": 0}
        agents[name]["total_slas"] += 1
        if sla["status"] == "healthy":
            agents[name]["healthy"] += 1
        else:
            agents[name]["breached"] += 1

    agent_summary = [
        {
            "agent_name": name,
            "total_slas": info["total_slas"],
            "healthy": info["healthy"],
            "breached": info["breached"],
            "status": "healthy" if info["breached"] == 0 else "breached",
        }
        for name, info in agents.items()
    ]

    return {
        "overall_status": status["overall_status"],
        "total_slas": status["total_slas"],
        "healthy": status["healthy"],
        "breached": status["breached"],
        "agent_summary": agent_summary,
        "sla_details": status["slas"],
        "recent_breaches_7d": breaches["total_breaches"],
        "recent_breaches": breaches["breaches"][:10],
    }
