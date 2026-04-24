"""
Compliance Export — One-click regulatory reports.

Generates compliance reports for LGPD, ISO 42001, and EU AI Act
by aggregating data from all ThinkNEO layers:
  - Trust Score, Guardrails, PII, Injection
  - Observability traces and alerts
  - Policy evaluations and violations
  - Outcome validation claims and proofs
  - Cost controls and routing
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
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
                cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'compliance_reports')")
                if not cur.fetchone()["exists"]:
                    import pathlib
                    for p in ["/app/migrations/008_compliance_export.sql",
                              "/opt/thinkneo-mcp-server/migrations/008_compliance_export.sql"]:
                        path = pathlib.Path(p)
                        if path.exists():
                            cur.execute(path.read_text())
                            logger.info("Compliance export tables created")
                            break
        _tables_checked = True
    except Exception as exc:
        logger.warning("Compliance table check failed: %s", exc)


# ---------------------------------------------------------------------------
# Data collectors — pull from all ThinkNEO layers
# ---------------------------------------------------------------------------

def _collect_data(cur, key_h: str, start: date, end: date) -> Dict[str, Any]:
    """Collect all governance data for the compliance period."""
    start_ts = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_ts = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)

    data = {}

    # Usage stats
    cur.execute(
        """
        SELECT COUNT(*) AS total_calls,
               COUNT(DISTINCT tool_name) AS tools_used,
               COUNT(DISTINCT DATE(called_at)) AS active_days,
               COALESCE(SUM(cost_estimate_usd), 0) AS total_cost
        FROM usage_log
        WHERE key_hash = %s AND called_at BETWEEN %s AND %s
        """,
        (key_h, start_ts, end_ts),
    )
    data["usage"] = dict(cur.fetchone())
    data["usage"]["total_cost"] = float(data["usage"]["total_cost"])

    # Guardrails, PII, Injection
    for tool, key in [
        ("thinkneo_evaluate_guardrail", "guardrail_evaluations"),
        ("thinkneo_check", "guardrail_checks_free"),
        ("thinkneo_check_pii_international", "pii_scans"),
        ("thinkneo_detect_injection", "injection_scans"),
    ]:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM usage_log WHERE key_hash = %s AND tool_name = %s AND called_at BETWEEN %s AND %s",
            (key_h, tool, start_ts, end_ts),
        )
        data[key] = cur.fetchone()["cnt"]

    # Observability sessions
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total_sessions,
                   COUNT(*) FILTER (WHERE status = 'success') AS successful,
                   COUNT(*) FILTER (WHERE status = 'failure') AS failed,
                   COALESCE(SUM(total_cost), 0) AS total_cost
            FROM agent_sessions
            WHERE api_key_hash = %s AND started_at BETWEEN %s AND %s
            """,
            (key_h, start_ts, end_ts),
        )
        data["observability"] = dict(cur.fetchone())
        data["observability"]["total_cost"] = float(data["observability"]["total_cost"])
    except Exception:
        data["observability"] = {"total_sessions": 0, "successful": 0, "failed": 0, "total_cost": 0}

    # Alerts
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total_alerts,
                   COUNT(*) FILTER (WHERE severity = 'critical') AS critical,
                   COUNT(*) FILTER (WHERE severity = 'warning') AS warnings
            FROM agent_alerts
            WHERE api_key_hash = %s AND created_at BETWEEN %s AND %s
            """,
            (key_h, start_ts, end_ts),
        )
        data["alerts"] = dict(cur.fetchone())
    except Exception:
        data["alerts"] = {"total_alerts": 0, "critical": 0, "warnings": 0}

    # Policy violations
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE effect = 'block') AS blocked,
                   COUNT(*) FILTER (WHERE effect = 'require_approval') AS approval_required,
                   COUNT(*) FILTER (WHERE resolved = TRUE) AS resolved
            FROM policy_violations
            WHERE api_key_hash = %s AND violated_at BETWEEN %s AND %s
            """,
            (key_h, start_ts, end_ts),
        )
        data["policy_violations"] = dict(cur.fetchone())
    except Exception:
        data["policy_violations"] = {"total": 0, "blocked": 0, "approval_required": 0, "resolved": 0}

    # Outcome validation
    try:
        cur.execute(
            """
            SELECT COUNT(*) AS total_claims,
                   COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                   COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                   COUNT(*) FILTER (WHERE status = 'expired') AS expired
            FROM outcome_claims
            WHERE api_key_hash = %s AND claimed_at BETWEEN %s AND %s
            """,
            (key_h, start_ts, end_ts),
        )
        data["outcome_validation"] = dict(cur.fetchone())
        total_decidable = data["outcome_validation"]["verified"] + data["outcome_validation"]["failed"]
        data["outcome_validation"]["verification_rate"] = round(
            data["outcome_validation"]["verified"] / total_decidable * 100 if total_decidable > 0 else 0, 1
        )
    except Exception:
        data["outcome_validation"] = {"total_claims": 0, "verified": 0, "failed": 0, "expired": 0, "verification_rate": 0}

    # Trust Score
    try:
        cur.execute(
            """
            SELECT score, badge_level, evaluated_at
            FROM trust_scores
            WHERE api_key_hash = %s
            ORDER BY evaluated_at DESC LIMIT 1
            """,
            (key_h,),
        )
        ts_row = cur.fetchone()
        if ts_row:
            data["trust_score"] = {
                "score": ts_row["score"],
                "badge_level": ts_row["badge_level"],
                "evaluated_at": ts_row["evaluated_at"].isoformat(),
            }
        else:
            data["trust_score"] = {"score": 0, "badge_level": "unrated", "evaluated_at": None}
    except Exception:
        data["trust_score"] = {"score": 0, "badge_level": "unrated", "evaluated_at": None}

    # Active policies
    try:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM policies WHERE api_key_hash = %s AND enabled = TRUE",
            (key_h,),
        )
        data["active_policies"] = cur.fetchone()["cnt"]
    except Exception:
        data["active_policies"] = 0

    return data


# ---------------------------------------------------------------------------
# Framework-specific report generators
# ---------------------------------------------------------------------------

def _generate_lgpd(data: Dict[str, Any], period_start: date, period_end: date) -> Dict[str, Any]:
    """Generate LGPD (Lei Geral de Protecao de Dados) compliance report."""
    pii_scans = data.get("pii_scans", 0)
    guardrails = data.get("guardrail_evaluations", 0) + data.get("guardrail_checks_free", 0)
    ov = data.get("outcome_validation", {})
    pv = data.get("policy_violations", {})
    ts = data.get("trust_score", {})

    # LGPD compliance scoring
    score = 0
    findings = []
    gaps = []

    # Art. 6 — Legal basis for processing
    if guardrails > 0:
        score += 15
        findings.append(f"Content safety guardrails active: {guardrails} evaluations")
    else:
        gaps.append("Art. 6: No content guardrail evaluations detected")

    # Art. 12 — Transparency
    if data["usage"]["total_calls"] > 0:
        score += 10
        findings.append(f"Full audit trail: {data['usage']['total_calls']} logged operations")
    else:
        gaps.append("Art. 12: No audit trail detected")

    # Art. 18 — Data subject rights (PII scanning)
    if pii_scans >= 10:
        score += 20
        findings.append(f"Active PII scanning: {pii_scans} scans in period")
    elif pii_scans >= 1:
        score += 10
        findings.append(f"PII scanning present: {pii_scans} scans")
        gaps.append("Art. 18: Increase PII scan frequency")
    else:
        gaps.append("Art. 18: No PII scanning detected — risk of undetected personal data processing")

    # Art. 46 — Security measures
    injection = data.get("injection_scans", 0)
    if injection >= 5:
        score += 15
        findings.append(f"Injection defense active: {injection} scans")
    elif injection >= 1:
        score += 8
        findings.append(f"Injection defense present: {injection} scans")
    else:
        gaps.append("Art. 46: No injection defense detected")

    # Art. 50 — Governance
    if data.get("active_policies", 0) > 0:
        score += 10
        findings.append(f"AI governance policies configured: {data['active_policies']} active")
    else:
        gaps.append("Art. 50: No AI governance policies configured")

    # Observability (accountability)
    obs = data.get("observability", {})
    if obs.get("total_sessions", 0) > 0:
        score += 10
        findings.append(f"Agent observability active: {obs['total_sessions']} traced sessions")
    else:
        gaps.append("Accountability: No agent observability traces")

    # Outcome validation (proof of correct processing)
    if ov.get("total_claims", 0) > 0:
        score += 10
        findings.append(f"Outcome validation active: {ov['verification_rate']}% verification rate")
    else:
        gaps.append("No outcome validation — cannot prove AI actions were correctly executed")

    # Trust Score
    if ts.get("score", 0) >= 60:
        score += 10
        findings.append(f"Trust Score: {ts['score']}/100 ({ts['badge_level']})")
    elif ts.get("score", 0) >= 40:
        score += 5
        findings.append(f"Trust Score: {ts['score']}/100 ({ts['badge_level']}) — needs improvement")
    else:
        gaps.append("Trust Score below acceptable threshold")

    score = min(score, 100)

    return {
        "framework": "LGPD",
        "framework_full": "Lei Geral de Protecao de Dados (Lei 13.709/2018)",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "compliance_score": score,
        "status": "compliant" if score >= 70 else "partially_compliant" if score >= 40 else "non_compliant",
        "sections": {
            "art_6_legal_basis": {"status": "pass" if guardrails > 0 else "fail", "guardrail_evaluations": guardrails},
            "art_12_transparency": {"status": "pass" if data["usage"]["total_calls"] > 0 else "fail", "audit_trail_entries": data["usage"]["total_calls"]},
            "art_18_data_subject_rights": {"status": "pass" if pii_scans >= 10 else "partial" if pii_scans >= 1 else "fail", "pii_scans": pii_scans},
            "art_46_security": {"status": "pass" if injection >= 5 else "partial" if injection >= 1 else "fail", "injection_scans": injection},
            "art_50_governance": {"status": "pass" if data.get("active_policies", 0) > 0 else "fail", "active_policies": data.get("active_policies", 0)},
        },
        "findings": findings,
        "gaps": gaps,
        "data_summary": data,
    }


def _generate_iso_42001(data: Dict[str, Any], period_start: date, period_end: date) -> Dict[str, Any]:
    """Generate ISO 42001 (AI Management System) compliance report."""
    score = 0
    findings = []
    gaps = []

    # Clause 4 — Context of the organization
    if data["usage"]["total_calls"] > 0:
        score += 10
        findings.append("AI system is actively monitored and governed")

    # Clause 5 — Leadership
    if data.get("active_policies", 0) > 0:
        score += 15
        findings.append(f"{data['active_policies']} governance policies defined")
    else:
        gaps.append("Clause 5: No governance policies defined")

    # Clause 6 — Planning (risk management)
    pv = data.get("policy_violations", {})
    if pv.get("total", 0) > 0:
        resolved_rate = pv.get("resolved", 0) / pv["total"] * 100 if pv["total"] > 0 else 0
        score += 10
        findings.append(f"Risk events tracked: {pv['total']} violations, {resolved_rate:.0f}% resolved")
    elif data.get("active_policies", 0) > 0:
        score += 5
        findings.append("Policies active but no violations recorded (may indicate low usage)")

    # Clause 7 — Support (resources & competence)
    if data["usage"]["tools_used"] >= 5:
        score += 10
        findings.append(f"Broad governance coverage: {data['usage']['tools_used']} tools used")
    elif data["usage"]["tools_used"] >= 1:
        score += 5

    # Clause 8 — Operation
    obs = data.get("observability", {})
    if obs.get("total_sessions", 0) >= 5:
        score += 15
        findings.append(f"Operational tracing: {obs['total_sessions']} agent sessions traced")
    elif obs.get("total_sessions", 0) >= 1:
        score += 8

    # Clause 9 — Performance evaluation
    ts = data.get("trust_score", {})
    ov = data.get("outcome_validation", {})
    if ts.get("score", 0) >= 60:
        score += 15
        findings.append(f"Performance measured: Trust Score {ts['score']}/100")
    elif ts.get("score", 0) >= 1:
        score += 5

    if ov.get("total_claims", 0) >= 5:
        score += 15
        findings.append(f"Outcome verification: {ov['verification_rate']}% rate over {ov['total_claims']} claims")
    elif ov.get("total_claims", 0) >= 1:
        score += 8

    # Clause 10 — Improvement
    guardrails = data.get("guardrail_evaluations", 0) + data.get("guardrail_checks_free", 0)
    if guardrails > 0 and data.get("injection_scans", 0) > 0:
        score += 10
        findings.append("Continuous improvement: guardrails + injection defense active")
    else:
        gaps.append("Clause 10: Missing continuous improvement mechanisms")

    score = min(score, 100)

    return {
        "framework": "ISO 42001",
        "framework_full": "ISO/IEC 42001:2023 — AI Management System",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "compliance_score": score,
        "status": "compliant" if score >= 70 else "partially_compliant" if score >= 40 else "non_compliant",
        "findings": findings,
        "gaps": gaps,
        "data_summary": data,
    }


def _generate_eu_ai_act(data: Dict[str, Any], period_start: date, period_end: date) -> Dict[str, Any]:
    """Generate EU AI Act compliance report."""
    score = 0
    findings = []
    gaps = []

    # Art. 9 — Risk Management
    pv = data.get("policy_violations", {})
    if data.get("active_policies", 0) > 0:
        score += 15
        findings.append(f"Risk management via {data['active_policies']} active policies")
    else:
        gaps.append("Art. 9: No AI risk management policies configured")

    # Art. 10 — Data Governance
    pii = data.get("pii_scans", 0)
    if pii >= 5:
        score += 15
        findings.append(f"Data governance: {pii} PII scans in period")
    elif pii >= 1:
        score += 8
    else:
        gaps.append("Art. 10: No PII scanning detected")

    # Art. 12 — Record-keeping
    if data["usage"]["total_calls"] >= 50:
        score += 15
        findings.append(f"Comprehensive audit trail: {data['usage']['total_calls']} entries over {data['usage']['active_days']} days")
    elif data["usage"]["total_calls"] >= 1:
        score += 8
    else:
        gaps.append("Art. 12: No audit records")

    # Art. 13 — Transparency
    obs = data.get("observability", {})
    if obs.get("total_sessions", 0) > 0:
        score += 10
        findings.append(f"Transparency: {obs['total_sessions']} traced agent sessions")
    else:
        gaps.append("Art. 13: No transparency mechanisms (agent tracing)")

    # Art. 14 — Human oversight
    if pv.get("approval_required", 0) > 0 or data.get("active_policies", 0) > 0:
        score += 15
        findings.append("Human oversight mechanisms in place via policy engine")
    else:
        gaps.append("Art. 14: No human-in-the-loop mechanisms detected")

    # Art. 15 — Accuracy, robustness, cybersecurity
    injection = data.get("injection_scans", 0)
    guardrails = data.get("guardrail_evaluations", 0) + data.get("guardrail_checks_free", 0)
    ov = data.get("outcome_validation", {})

    if injection > 0 and guardrails > 0:
        score += 10
        findings.append(f"Security: {guardrails} guardrails + {injection} injection scans")

    if ov.get("verification_rate", 0) >= 80:
        score += 10
        findings.append(f"Accuracy verified: {ov['verification_rate']}% outcome verification rate")
    elif ov.get("total_claims", 0) > 0:
        score += 5

    # Trust Score
    ts = data.get("trust_score", {})
    if ts.get("score", 0) >= 60:
        score += 10
        findings.append(f"Overall AI governance: Trust Score {ts['score']}/100")

    score = min(score, 100)

    return {
        "framework": "EU AI Act",
        "framework_full": "Regulation (EU) 2024/1689 — Artificial Intelligence Act",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "compliance_score": score,
        "status": "compliant" if score >= 70 else "partially_compliant" if score >= 40 else "non_compliant",
        "findings": findings,
        "gaps": gaps,
        "data_summary": data,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

GENERATORS = {
    "lgpd": _generate_lgpd,
    "iso_42001": _generate_iso_42001,
    "eu_ai_act": _generate_eu_ai_act,
}


def generate_compliance_report(
    api_key: str,
    framework: str,
    days: int = 30,
) -> Dict[str, Any]:
    """Generate a compliance report for the specified framework."""
    _ensure_tables()
    key_h = hash_key(api_key)

    if framework not in GENERATORS:
        raise ValueError(f"Unsupported framework '{framework}'. Supported: {sorted(GENERATORS.keys())}")

    period_end = date.today()
    period_start = period_end - timedelta(days=days)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Collect all governance data
                data = _collect_data(cur, key_h, period_start, period_end)

                # Generate framework-specific report
                generator = GENERATORS[framework]
                report = generator(data, period_start, period_end)

                # Create hash for integrity
                report_json = json.dumps(report, sort_keys=True, default=str)
                report_hash = hashlib.sha256(report_json.encode()).hexdigest()
                download_token = secrets.token_urlsafe(24)

                # Store report
                cur.execute(
                    """
                    INSERT INTO compliance_reports
                        (api_key_hash, framework, period_start, period_end,
                         report_data, compliance_score, report_hash, download_token)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                    RETURNING report_id, generated_at
                    """,
                    (
                        key_h, framework, period_start, period_end,
                        report_json, report["compliance_score"],
                        report_hash, download_token,
                    ),
                )
                result = cur.fetchone()

                report["report_id"] = str(result["report_id"])
                report["report_hash"] = report_hash
                report["hash_algorithm"] = "sha256"
                report["tamper_evident"] = True
                report["download_token"] = download_token
                report["download_url"] = f"https://mcp.thinkneo.ai/compliance/{download_token}"
                report["generated_at"] = result["generated_at"].isoformat()

                return report

    except ValueError:
        raise
    except Exception as exc:
        logger.error("generate_compliance_report failed: %s", exc)
        raise


def list_compliance_reports(api_key: str, limit: int = 20) -> Dict[str, Any]:
    """List previously generated compliance reports."""
    _ensure_tables()
    key_h = hash_key(api_key)

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT report_id, framework, period_start, period_end,
                           compliance_score, report_hash, download_token, generated_at
                    FROM compliance_reports
                    WHERE api_key_hash = %s
                    ORDER BY generated_at DESC
                    LIMIT %s
                    """,
                    (key_h, limit),
                )
                reports = []
                for r in cur.fetchall():
                    reports.append({
                        "report_id": str(r["report_id"]),
                        "framework": r["framework"],
                        "period": f"{r['period_start']} to {r['period_end']}",
                        "compliance_score": float(r["compliance_score"]),
                        "report_hash": r["report_hash"],
                        "download_url": f"https://mcp.thinkneo.ai/compliance/{r['download_token']}",
                        "generated_at": r["generated_at"].isoformat(),
                    })

                return {"total_reports": len(reports), "reports": reports}

    except Exception as exc:
        logger.error("list_compliance_reports failed: %s", exc)
        raise
