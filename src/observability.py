"""
Observability Engine — "Datadog for AI Agents"

Core logic for tracing, monitoring, and auditing every AI agent action:
- Session tracking: start/end agent sessions with context
- Event ingestion: log each tool call, model call, decision point
- Real-time aggregation: hourly metrics computation
- Alert engine: detect anomalies (cost spike >3x avg, error rate >20%,
  PII access without guardrail, unusual tool patterns)
- Timeline reconstruction: given a session_id, return ordered list of events
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def start_session(
    api_key: str,
    agent_name: str,
    agent_type: str = "generic",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new agent session and return session_id + trace_url."""
    key_h = hash_key(api_key)
    session_id = str(uuid.uuid4())
    meta = metadata or {}

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_sessions
                        (session_id, api_key_hash, agent_name, agent_type, metadata)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING session_id, started_at
                    """,
                    (session_id, key_h, agent_name, agent_type, _json_dumps(meta)),
                )
                row = cur.fetchone()
                return {
                    "session_id": str(row["session_id"]),
                    "started_at": row["started_at"].isoformat(),
                    "trace_url": f"https://mcp.thinkneo.ai/traces/{session_id}",
                }
    except Exception as exc:
        logger.error("start_session failed: %s", exc)
        raise


def end_session(
    session_id: str,
    status: str = "success",
) -> Dict[str, Any]:
    """End an agent session and return summary stats."""
    if status not in ("success", "failure", "timeout"):
        status = "success"

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Compute aggregates from events
                cur.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE event_type = 'tool_call') AS tool_calls,
                        COUNT(*) FILTER (WHERE event_type = 'model_call') AS model_calls,
                        COUNT(*) AS total_events,
                        COALESCE(SUM(cost), 0) AS total_cost,
                        COALESCE(AVG(latency_ms), 0) AS avg_latency_ms
                    FROM agent_events
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                stats = cur.fetchone()

                # Update the session
                cur.execute(
                    """
                    UPDATE agent_sessions
                    SET ended_at = NOW(),
                        status = %s,
                        total_cost = %s,
                        total_tool_calls = %s,
                        total_model_calls = %s
                    WHERE session_id = %s
                    RETURNING started_at, ended_at
                    """,
                    (
                        status,
                        float(stats["total_cost"]),
                        stats["tool_calls"],
                        stats["model_calls"],
                        session_id,
                    ),
                )
                session_row = cur.fetchone()
                if not session_row:
                    raise ValueError(f"Session {session_id} not found")

                duration_s = (
                    session_row["ended_at"] - session_row["started_at"]
                ).total_seconds()

                # Trigger post-session alert checks
                _check_session_alerts(conn, session_id)

                return {
                    "session_id": session_id,
                    "status": status,
                    "duration_seconds": round(duration_s, 2),
                    "total_cost_usd": round(float(stats["total_cost"]), 6),
                    "total_tool_calls": stats["tool_calls"],
                    "total_model_calls": stats["model_calls"],
                    "total_events": stats["total_events"],
                    "avg_latency_ms": round(float(stats["avg_latency_ms"]), 1),
                }
    except ValueError:
        raise
    except Exception as exc:
        logger.error("end_session failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Event ingestion
# ---------------------------------------------------------------------------

def log_event(
    session_id: str,
    event_type: str,
    tool_name: Optional[str] = None,
    model_name: Optional[str] = None,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    cost: float = 0.0,
    latency_ms: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Log an event within an agent session. Returns event_id + running cost."""
    valid_types = {"tool_call", "model_call", "decision", "error", "pii_access", "guardrail_triggered"}
    if event_type not in valid_types:
        raise ValueError(f"Invalid event_type '{event_type}'. Must be one of: {valid_types}")

    meta = metadata or {}

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Verify session exists and is active
                cur.execute(
                    "SELECT status, api_key_hash FROM agent_sessions WHERE session_id = %s",
                    (session_id,),
                )
                session = cur.fetchone()
                if not session:
                    raise ValueError(f"Session {session_id} not found")
                if session["status"] != "active":
                    raise ValueError(f"Session {session_id} is already {session['status']}")

                # Insert event
                cur.execute(
                    """
                    INSERT INTO agent_events
                        (session_id, event_type, tool_name, model_name,
                         input_summary, output_summary, cost, latency_ms, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id, timestamp
                    """,
                    (
                        session_id, event_type, tool_name, model_name,
                        _truncate(input_summary, 500), _truncate(output_summary, 500),
                        cost, latency_ms, _json_dumps(meta),
                    ),
                )
                event_row = cur.fetchone()

                # Running session cost
                cur.execute(
                    "SELECT COALESCE(SUM(cost), 0) AS running_cost FROM agent_events WHERE session_id = %s",
                    (session_id,),
                )
                cost_row = cur.fetchone()

                # Real-time alert checks for specific event types
                _check_event_alerts(
                    conn, session_id, session["api_key_hash"],
                    event_type, event_row["id"], cost,
                )

                return {
                    "event_id": event_row["id"],
                    "timestamp": event_row["timestamp"].isoformat(),
                    "running_session_cost_usd": round(float(cost_row["running_cost"]), 6),
                }
    except ValueError:
        raise
    except Exception as exc:
        logger.error("log_event failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Timeline / trace retrieval
# ---------------------------------------------------------------------------

def get_trace(session_id: str) -> Dict[str, Any]:
    """Reconstruct the full trace for a session: timeline of events + alerts."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Session info
                cur.execute(
                    "SELECT * FROM agent_sessions WHERE session_id = %s",
                    (session_id,),
                )
                session = cur.fetchone()
                if not session:
                    raise ValueError(f"Session {session_id} not found")

                # Events timeline
                cur.execute(
                    """
                    SELECT id, event_type, timestamp, tool_name, model_name,
                           input_summary, output_summary, cost, latency_ms, metadata
                    FROM agent_events
                    WHERE session_id = %s
                    ORDER BY timestamp ASC
                    """,
                    (session_id,),
                )
                events = []
                for row in cur.fetchall():
                    events.append({
                        "event_id": row["id"],
                        "event_type": row["event_type"],
                        "timestamp": row["timestamp"].isoformat(),
                        "tool_name": row["tool_name"],
                        "model_name": row["model_name"],
                        "input_summary": row["input_summary"],
                        "output_summary": row["output_summary"],
                        "cost_usd": round(float(row["cost"]), 6),
                        "latency_ms": row["latency_ms"],
                        "metadata": row["metadata"] or {},
                    })

                # Alerts for this session
                cur.execute(
                    """
                    SELECT id, alert_type, severity, message, event_id,
                           created_at, acknowledged_at
                    FROM agent_alerts
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
                alerts = []
                for row in cur.fetchall():
                    alerts.append({
                        "alert_id": row["id"],
                        "alert_type": row["alert_type"],
                        "severity": row["severity"],
                        "message": row["message"],
                        "event_id": row["event_id"],
                        "created_at": row["created_at"].isoformat(),
                        "acknowledged": row["acknowledged_at"] is not None,
                    })

                duration_s = None
                if session["ended_at"] and session["started_at"]:
                    duration_s = round(
                        (session["ended_at"] - session["started_at"]).total_seconds(), 2
                    )

                return {
                    "session_id": str(session["session_id"]),
                    "agent_name": session["agent_name"],
                    "agent_type": session["agent_type"],
                    "status": session["status"],
                    "started_at": session["started_at"].isoformat(),
                    "ended_at": session["ended_at"].isoformat() if session["ended_at"] else None,
                    "duration_seconds": duration_s,
                    "total_cost_usd": round(float(session["total_cost"]), 6),
                    "total_tool_calls": session["total_tool_calls"],
                    "total_model_calls": session["total_model_calls"],
                    "metadata": session["metadata"] or {},
                    "events_count": len(events),
                    "events": events,
                    "alerts_count": len(alerts),
                    "alerts": alerts,
                }
    except ValueError:
        raise
    except Exception as exc:
        logger.error("get_trace failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Dashboard aggregation
# ---------------------------------------------------------------------------

_PERIOD_MAP = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def get_dashboard(api_key: str, period: str = "24h") -> Dict[str, Any]:
    """
    Aggregate observability dashboard data for the given period.
    Returns totals, error rate, top agents/tools, active alerts, cost trend.
    """
    delta = _PERIOD_MAP.get(period, timedelta(hours=24))
    since = datetime.now(timezone.utc) - delta
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Total sessions and status breakdown
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS total_sessions,
                        COUNT(*) FILTER (WHERE status = 'success') AS successful,
                        COUNT(*) FILTER (WHERE status = 'failure') AS failed,
                        COUNT(*) FILTER (WHERE status = 'active') AS active,
                        COUNT(*) FILTER (WHERE status = 'timeout') AS timed_out,
                        COALESCE(SUM(total_cost), 0) AS total_cost
                    FROM agent_sessions
                    WHERE api_key_hash = %s AND started_at >= %s
                    """,
                    (key_h, since),
                )
                sess = cur.fetchone()

                # Total events + error rate + avg latency
                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS total_events,
                        COUNT(*) FILTER (WHERE event_type = 'error') AS errors,
                        COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                        COALESCE(SUM(cost), 0) AS event_cost
                    FROM agent_events e
                    JOIN agent_sessions s ON e.session_id = s.session_id
                    WHERE s.api_key_hash = %s AND e.timestamp >= %s
                    """,
                    (key_h, since),
                )
                ev = cur.fetchone()

                total_events = ev["total_events"]
                error_rate = round(
                    (ev["errors"] / total_events * 100) if total_events > 0 else 0, 2
                )

                # Top agents
                cur.execute(
                    """
                    SELECT agent_name, COUNT(*) AS sessions,
                           COALESCE(SUM(total_cost), 0) AS cost
                    FROM agent_sessions
                    WHERE api_key_hash = %s AND started_at >= %s
                    GROUP BY agent_name
                    ORDER BY sessions DESC
                    LIMIT 10
                    """,
                    (key_h, since),
                )
                top_agents = [
                    {"agent": r["agent_name"], "sessions": r["sessions"],
                     "cost_usd": round(float(r["cost"]), 6)}
                    for r in cur.fetchall()
                ]

                # Top tools
                cur.execute(
                    """
                    SELECT e.tool_name, COUNT(*) AS calls,
                           COALESCE(SUM(e.cost), 0) AS cost,
                           COALESCE(AVG(e.latency_ms), 0) AS avg_latency
                    FROM agent_events e
                    JOIN agent_sessions s ON e.session_id = s.session_id
                    WHERE s.api_key_hash = %s AND e.timestamp >= %s
                      AND e.tool_name IS NOT NULL
                    GROUP BY e.tool_name
                    ORDER BY calls DESC
                    LIMIT 10
                    """,
                    (key_h, since),
                )
                top_tools = [
                    {"tool": r["tool_name"], "calls": r["calls"],
                     "cost_usd": round(float(r["cost"]), 6),
                     "avg_latency_ms": round(float(r["avg_latency"]), 1)}
                    for r in cur.fetchall()
                ]

                # Active alerts (unacknowledged)
                cur.execute(
                    """
                    SELECT id, alert_type, severity, message, session_id, created_at
                    FROM agent_alerts
                    WHERE api_key_hash = %s AND acknowledged_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    (key_h,),
                )
                active_alerts = [
                    {
                        "alert_id": r["id"],
                        "type": r["alert_type"],
                        "severity": r["severity"],
                        "message": r["message"],
                        "session_id": str(r["session_id"]) if r["session_id"] else None,
                        "created_at": r["created_at"].isoformat(),
                    }
                    for r in cur.fetchall()
                ]

                # Cost trend — hourly buckets for the period
                cur.execute(
                    """
                    SELECT
                        date_trunc('hour', e.timestamp) AS hour,
                        COALESCE(SUM(e.cost), 0) AS cost,
                        COUNT(*) AS events
                    FROM agent_events e
                    JOIN agent_sessions s ON e.session_id = s.session_id
                    WHERE s.api_key_hash = %s AND e.timestamp >= %s
                    GROUP BY date_trunc('hour', e.timestamp)
                    ORDER BY hour ASC
                    """,
                    (key_h, since),
                )
                cost_trend = [
                    {
                        "hour": r["hour"].isoformat(),
                        "cost_usd": round(float(r["cost"]), 6),
                        "events": r["events"],
                    }
                    for r in cur.fetchall()
                ]

                # Refresh hourly metrics (upsert for current hour)
                _refresh_hourly_metrics(cur, key_h)

                return {
                    "period": period,
                    "since": since.isoformat(),
                    "total_sessions": sess["total_sessions"],
                    "sessions_breakdown": {
                        "successful": sess["successful"],
                        "failed": sess["failed"],
                        "active": sess["active"],
                        "timed_out": sess["timed_out"],
                    },
                    "total_events": total_events,
                    "total_cost_usd": round(float(sess["total_cost"]), 6),
                    "error_rate_pct": error_rate,
                    "avg_latency_ms": round(float(ev["avg_latency_ms"]), 1),
                    "top_agents": top_agents,
                    "top_tools": top_tools,
                    "active_alerts": active_alerts,
                    "active_alerts_count": len(active_alerts),
                    "cost_trend": cost_trend,
                    "dashboard_url": "https://mcp.thinkneo.ai/observability",
                }
    except Exception as exc:
        logger.error("get_dashboard failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Alert engine
# ---------------------------------------------------------------------------

def _check_event_alerts(
    conn, session_id: str, api_key_hash: str,
    event_type: str, event_id: int, cost: float,
) -> None:
    """Real-time alert checks triggered on each event."""
    try:
        with conn.cursor() as cur:
            # PII access without guardrail in same session
            if event_type == "pii_access":
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt FROM agent_events
                    WHERE session_id = %s AND event_type = 'guardrail_triggered'
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if row["cnt"] == 0:
                    _create_alert(
                        cur, api_key_hash, "pii_violation", "warning",
                        f"PII access detected in session {session_id} without prior guardrail check.",
                        session_id, event_id,
                    )

            # Single-event cost spike (>$1 per event is suspicious)
            if cost > 1.0:
                _create_alert(
                    cur, api_key_hash, "anomaly", "warning",
                    f"High-cost event detected: ${cost:.4f} in session {session_id}.",
                    session_id, event_id,
                )

            # Error spike: >5 errors in the last 10 minutes for this key
            if event_type == "error":
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM agent_events e
                    JOIN agent_sessions s ON e.session_id = s.session_id
                    WHERE s.api_key_hash = %s
                      AND e.event_type = 'error'
                      AND e.timestamp >= NOW() - INTERVAL '10 minutes'
                    """,
                    (api_key_hash,),
                )
                row = cur.fetchone()
                if row["cnt"] >= 5:
                    # Only create if not already alerted in last 10 min
                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt FROM agent_alerts
                        WHERE api_key_hash = %s AND alert_type = 'error_spike'
                          AND created_at >= NOW() - INTERVAL '10 minutes'
                        """,
                        (api_key_hash,),
                    )
                    existing = cur.fetchone()
                    if existing["cnt"] == 0:
                        _create_alert(
                            cur, api_key_hash, "error_spike", "critical",
                            f"Error spike detected: {row['cnt']} errors in last 10 minutes.",
                            session_id, event_id,
                        )
    except Exception as exc:
        logger.warning("_check_event_alerts failed (non-fatal): %s", exc)


def _check_session_alerts(conn, session_id: str) -> None:
    """Post-session alert checks: cost anomaly, error rate anomaly."""
    try:
        with conn.cursor() as cur:
            # Get this session's stats
            cur.execute(
                "SELECT * FROM agent_sessions WHERE session_id = %s",
                (session_id,),
            )
            session = cur.fetchone()
            if not session:
                return

            key_h = session["api_key_hash"]
            session_cost = float(session["total_cost"])

            # Cost anomaly: session cost > 3x the average of last 50 sessions
            cur.execute(
                """
                SELECT COALESCE(AVG(total_cost), 0) AS avg_cost
                FROM (
                    SELECT total_cost FROM agent_sessions
                    WHERE api_key_hash = %s AND session_id != %s
                      AND status IN ('success', 'failure')
                    ORDER BY ended_at DESC
                    LIMIT 50
                ) recent
                """,
                (key_h, session_id),
            )
            avg_row = cur.fetchone()
            avg_cost = float(avg_row["avg_cost"])
            if avg_cost > 0 and session_cost > avg_cost * 3:
                _create_alert(
                    cur, key_h, "budget_exceeded", "warning",
                    f"Session {session_id} cost ${session_cost:.4f} is {session_cost/avg_cost:.1f}x the average (${avg_cost:.4f}).",
                    session_id, None,
                )

            # Error rate anomaly: >20% of events in this session were errors
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE event_type = 'error') AS errors
                FROM agent_events
                WHERE session_id = %s
                """,
                (session_id,),
            )
            ev = cur.fetchone()
            if ev["total"] > 0:
                err_rate = ev["errors"] / ev["total"]
                if err_rate > 0.20:
                    _create_alert(
                        cur, key_h, "anomaly", "warning",
                        f"High error rate ({err_rate:.0%}) in session {session_id}: {ev['errors']}/{ev['total']} events were errors.",
                        session_id, None,
                    )
    except Exception as exc:
        logger.warning("_check_session_alerts failed (non-fatal): %s", exc)


def _create_alert(
    cur, api_key_hash: str, alert_type: str, severity: str,
    message: str, session_id: Optional[str], event_id: Optional[int],
) -> None:
    """Insert an alert record."""
    cur.execute(
        """
        INSERT INTO agent_alerts
            (api_key_hash, alert_type, severity, message, session_id, event_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (api_key_hash, alert_type, severity, message, session_id, event_id),
    )
    logger.warning("ALERT [%s/%s] %s", severity, alert_type, message)


# ---------------------------------------------------------------------------
# Hourly metrics refresh
# ---------------------------------------------------------------------------

def _refresh_hourly_metrics(cur, api_key_hash: str) -> None:
    """Upsert the current hour's metrics from live data."""
    try:
        cur.execute(
            """
            INSERT INTO agent_metrics_hourly (hour, api_key_hash, requests, errors, total_cost, avg_latency_ms, unique_agents, unique_tools)
            SELECT
                date_trunc('hour', NOW()) AS hour,
                %s AS api_key_hash,
                COUNT(DISTINCT e.id) AS requests,
                COUNT(DISTINCT e.id) FILTER (WHERE e.event_type = 'error') AS errors,
                COALESCE(SUM(e.cost), 0) AS total_cost,
                COALESCE(AVG(e.latency_ms), 0) AS avg_latency_ms,
                COUNT(DISTINCT s.agent_name) AS unique_agents,
                COUNT(DISTINCT e.tool_name) FILTER (WHERE e.tool_name IS NOT NULL) AS unique_tools
            FROM agent_events e
            JOIN agent_sessions s ON e.session_id = s.session_id
            WHERE s.api_key_hash = %s
              AND e.timestamp >= date_trunc('hour', NOW())
              AND e.timestamp < date_trunc('hour', NOW()) + INTERVAL '1 hour'
            ON CONFLICT (hour, api_key_hash)
            DO UPDATE SET
                requests = EXCLUDED.requests,
                errors = EXCLUDED.errors,
                total_cost = EXCLUDED.total_cost,
                avg_latency_ms = EXCLUDED.avg_latency_ms,
                unique_agents = EXCLUDED.unique_agents,
                unique_tools = EXCLUDED.unique_tools
            """,
            (api_key_hash, api_key_hash),
        )
    except Exception as exc:
        logger.warning("_refresh_hourly_metrics failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: Optional[str], max_len: int) -> Optional[str]:
    """Truncate text to max_len chars."""
    if text is None:
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _json_dumps(obj: Any) -> str:
    """Safe JSON serialization."""
    import json
    return json.dumps(obj, default=str, ensure_ascii=False)
