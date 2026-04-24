"""
Tools: thinkneo_evaluate_trust_score, thinkneo_get_trust_badge

AI Trust Score — a quantifiable score (0-100) that measures how well-governed
an organization's AI stack is. Like a credit score but for AI deployments.

Categories (10, total 100 points):
  - Guardrails          (10 pts)
  - PII Protection       (8 pts)
  - Injection Defense    (8 pts)
  - Audit Trail         (10 pts)
  - Compliance          (12 pts)
  - Model Governance    (10 pts)
  - Cost Controls       (10 pts)
  - Outcome Validation  (14 pts) — "From Prompt to Proof"
  - Observability       (12 pts)
  - Smart Routing        (6 pts)

Badge levels:
  90-100  Platinum
  75-89   Gold
  60-74   Silver
  40-59   Bronze
  0-39    Unrated
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import get_bearer_token, require_auth
from ..database import _get_conn, hash_key, ensure_api_key
from ._common import utcnow

# ---------------------------------------------------------------------------
# Badge level thresholds
# ---------------------------------------------------------------------------

def _badge_level(score: int) -> str:
    if score >= 90:
        return "platinum"
    elif score >= 75:
        return "gold"
    elif score >= 60:
        return "silver"
    elif score >= 40:
        return "bronze"
    return "unrated"


BADGE_LABELS = {
    "platinum": "Platinum",
    "gold": "Gold",
    "silver": "Silver",
    "bronze": "Bronze",
    "unrated": "Unrated",
}


# ---------------------------------------------------------------------------
# Helper: count tool calls in usage_log
# ---------------------------------------------------------------------------

def _count_tool_calls(cur, key_hash: str, tool_names: list, days: int = 30) -> int:
    """Count usage_log entries for any of the given tool names in the last N days."""
    if not tool_names:
        return 0
    placeholders = ",".join(["%s"] * len(tool_names))
    cur.execute(
        f"""
        SELECT COUNT(*) as cnt FROM usage_log
        WHERE key_hash = %s
          AND tool_name IN ({placeholders})
          AND called_at >= NOW() - INTERVAL '{days} days'
        """,
        (key_hash, *tool_names),
    )
    row = cur.fetchone()
    return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# Scoring engine — 10 categories
# ---------------------------------------------------------------------------

def _score_guardrails(key_hash: str) -> Dict[str, Any]:
    """Guardrails usage: evaluate_guardrail + check (free tier)."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_evaluate_guardrail", "thinkneo_check",
                ])

                if calls >= 50:
                    score = 10
                    findings.append(f"Active guardrail usage: {calls} evaluations in 30 days")
                elif calls >= 15:
                    score = 7
                    findings.append(f"Good guardrail usage: {calls} evaluations in 30 days")
                elif calls >= 5:
                    score = 4
                    findings.append(f"Moderate guardrail usage: {calls} evaluations")
                    recommendations.append("Increase guardrail evaluation frequency")
                elif calls >= 1:
                    score = 2
                    findings.append(f"Minimal guardrail usage: {calls} evaluations")
                    recommendations.append("Integrate guardrail checks into your AI pipeline")
                else:
                    findings.append("No guardrail evaluations detected")
                    recommendations.append("Enable guardrail evaluation in your AI pipeline")
    except Exception:
        findings.append("Unable to assess guardrail configuration")

    return {"score": score, "max": 10, "findings": findings, "recommendations": recommendations}


def _score_pii_protection(key_hash: str) -> Dict[str, Any]:
    """PII detection tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_check_pii_international",
                ])

                if calls >= 30:
                    score = 8
                    findings.append(f"Active PII scanning: {calls} checks")
                elif calls >= 10:
                    score = 5
                    findings.append(f"Good PII scanning: {calls} checks")
                elif calls >= 1:
                    score = 3
                    findings.append(f"Minimal PII scanning: {calls} checks")
                    recommendations.append("Increase PII scanning frequency")
                else:
                    findings.append("No PII scanning detected")
                    recommendations.append("Enable PII detection to protect sensitive data")
    except Exception:
        findings.append("Unable to assess PII protection")

    return {"score": score, "max": 8, "findings": findings, "recommendations": recommendations}


def _score_injection_defense(key_hash: str) -> Dict[str, Any]:
    """Injection detection tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_detect_injection",
                ])

                if calls >= 30:
                    score = 8
                    findings.append(f"Active injection defense: {calls} scans")
                elif calls >= 10:
                    score = 5
                    findings.append(f"Good injection defense: {calls} scans")
                elif calls >= 1:
                    score = 3
                    findings.append(f"Minimal injection defense: {calls} scans")
                    recommendations.append("Scan all untrusted inputs for injection")
                else:
                    findings.append("No injection scanning detected")
                    recommendations.append("Enable prompt injection detection")
    except Exception:
        findings.append("Unable to assess injection defense")

    return {"score": score, "max": 8, "findings": findings, "recommendations": recommendations}


def _score_audit_trail(key_hash: str) -> Dict[str, Any]:
    """Audit trail: total calls, diversity, active days, freshness."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt,
                           COUNT(DISTINCT tool_name) as tools_used,
                           COUNT(DISTINCT DATE(called_at)) as active_days,
                           MAX(called_at) as last_call
                    FROM usage_log
                    WHERE key_hash = %s
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                total_calls = row["cnt"] if row else 0
                tools_used = row["tools_used"] if row else 0
                active_days = row["active_days"] if row else 0
                last_call = row["last_call"]

                # Volume + consistency (5 pts)
                if total_calls >= 100 and active_days >= 15:
                    score += 5
                    findings.append(f"Strong audit trail: {total_calls} events across {active_days} days")
                elif total_calls >= 30:
                    score += 3
                    findings.append(f"Moderate audit trail: {total_calls} events across {active_days} days")
                elif total_calls >= 5:
                    score += 1
                    findings.append(f"Minimal audit trail: {total_calls} events")
                    recommendations.append("Increase governance monitoring frequency")
                else:
                    findings.append("No significant audit trail")
                    recommendations.append("Start using governance tools to build audit trail")

                # Tool diversity (3 pts)
                if tools_used >= 8:
                    score += 3
                    findings.append(f"Broad coverage: {tools_used} different tools used")
                elif tools_used >= 4:
                    score += 2
                    findings.append(f"Moderate coverage: {tools_used} tools used")
                elif tools_used >= 1:
                    score += 1
                    findings.append(f"Limited coverage: {tools_used} tools")
                    recommendations.append("Explore more governance tools")

                # Freshness (2 pts)
                if last_call:
                    hours_since = (datetime.now(timezone.utc) - last_call.replace(tzinfo=timezone.utc if last_call.tzinfo is None else last_call.tzinfo)).total_seconds() / 3600
                    if hours_since < 24:
                        score += 2
                        findings.append("Audit trail is fresh (< 24h)")
                    elif hours_since < 168:
                        score += 1
                        findings.append("Recent activity (< 7 days)")
                    else:
                        recommendations.append("Resume regular governance monitoring")

                score = min(score, 10)

    except Exception:
        findings.append("Unable to assess audit trail")

    return {"score": score, "max": 10, "findings": findings, "recommendations": recommendations}


def _score_compliance(key_hash: str) -> Dict[str, Any]:
    """Compliance status, policy checks, secret scanning."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                compliance_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_get_compliance_status",
                ])
                policy_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_check_policy", "thinkneo_policy_evaluate",
                    "thinkneo_policy_list", "thinkneo_a2a_set_policy",
                ])
                secret_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_scan_secrets",
                ])

                # Compliance checks (5 pts)
                if compliance_calls >= 5:
                    score += 5
                    findings.append(f"Active compliance monitoring: {compliance_calls} checks")
                elif compliance_calls >= 1:
                    score += 3
                    findings.append(f"Compliance monitoring active: {compliance_calls} checks")
                else:
                    findings.append("No compliance checks detected")
                    recommendations.append("Run compliance checks regularly")

                # Policy enforcement (4 pts)
                if policy_calls >= 10:
                    score += 4
                    findings.append(f"Active policy enforcement: {policy_calls} evaluations")
                elif policy_calls >= 1:
                    score += 2
                    findings.append(f"Policy checks active: {policy_calls}")
                else:
                    findings.append("No policy enforcement detected")
                    recommendations.append("Configure AI policies")

                # Secret scanning (3 pts)
                if secret_calls >= 3:
                    score += 3
                    findings.append(f"Active secret scanning: {secret_calls} scans")
                elif secret_calls >= 1:
                    score += 1
                    findings.append(f"Secret scanning active: {secret_calls}")
                else:
                    recommendations.append("Scan for exposed secrets in prompts")

                score = min(score, 12)

    except Exception:
        findings.append("Unable to assess compliance")

    return {"score": score, "max": 12, "findings": findings, "recommendations": recommendations}


def _score_model_governance(key_hash: str) -> Dict[str, Any]:
    """Model governance: provider monitoring, model comparison, prompt optimization."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                provider_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_provider_status",
                ])
                routing_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_route_model", "thinkneo_simulate_savings",
                ])
                governance_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_compare_models", "thinkneo_optimize_prompt",
                    "thinkneo_detect_waste", "thinkneo_set_baseline",
                ])

                # Provider monitoring (4 pts)
                if provider_calls >= 5:
                    score += 4
                    findings.append(f"Active provider monitoring: {provider_calls} checks")
                elif provider_calls >= 1:
                    score += 2
                    findings.append(f"Provider monitoring: {provider_calls} checks")
                else:
                    recommendations.append("Monitor provider health regularly")

                # Smart routing (3 pts)
                if routing_calls >= 5:
                    score += 3
                    findings.append(f"Smart routing active: {routing_calls} routing decisions")
                elif routing_calls >= 1:
                    score += 2
                    findings.append(f"Routing used: {routing_calls} decisions")
                else:
                    recommendations.append("Use smart routing for cost-optimized model selection")

                # Advanced governance (3 pts)
                if governance_calls >= 3:
                    score += 3
                    findings.append(f"Advanced governance tools active: {governance_calls} uses")
                elif governance_calls >= 1:
                    score += 1
                    findings.append(f"Some advanced governance: {governance_calls} uses")
                else:
                    recommendations.append("Use waste detection and baseline tools")

                score = min(score, 10)

    except Exception:
        findings.append("Unable to assess model governance")

    return {"score": score, "max": 10, "findings": findings, "recommendations": recommendations}


def _score_cost_controls(key_hash: str) -> Dict[str, Any]:
    """Cost controls: budget, spend, alerts, savings."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                budget_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_get_budget_status",
                ])
                spend_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_check_spend", "thinkneo_get_savings_report",
                    "thinkneo_decision_cost", "thinkneo_agent_roi",
                ])
                alert_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_list_alerts",
                ])

                # Budget monitoring (4 pts)
                if budget_calls >= 5:
                    score += 4
                    findings.append(f"Active budget monitoring: {budget_calls} checks")
                elif budget_calls >= 1:
                    score += 2
                    findings.append(f"Budget monitoring: {budget_calls} checks")
                else:
                    findings.append("No budget monitoring")
                    recommendations.append("Set and monitor AI spend limits")

                # Spend tracking (4 pts)
                if spend_calls >= 5:
                    score += 4
                    findings.append(f"Active cost tracking: {spend_calls} reports")
                elif spend_calls >= 1:
                    score += 2
                    findings.append(f"Cost tracking: {spend_calls} reports")
                else:
                    findings.append("No spend tracking")
                    recommendations.append("Monitor AI costs regularly")

                # Alert monitoring (2 pts)
                if alert_calls >= 3:
                    score += 2
                    findings.append(f"Alert monitoring active: {alert_calls} checks")
                elif alert_calls >= 1:
                    score += 1
                    findings.append(f"Alert monitoring: {alert_calls} checks")
                else:
                    recommendations.append("Monitor alerts for cost anomalies")

                score = min(score, 10)

    except Exception:
        findings.append("Unable to assess cost controls")

    return {"score": score, "max": 10, "findings": findings, "recommendations": recommendations}


def _score_outcome_validation(key_hash: str) -> Dict[str, Any]:
    """Outcome Validation: claims registered, verified, verification rate."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Tool usage
                claim_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_register_claim", "thinkneo_verify_claim",
                    "thinkneo_get_proof", "thinkneo_verification_dashboard",
                ])

                # Tool usage score (6 pts)
                if claim_calls >= 20:
                    score += 6
                    findings.append(f"Active outcome validation: {claim_calls} operations")
                elif claim_calls >= 5:
                    score += 4
                    findings.append(f"Good outcome validation: {claim_calls} operations")
                elif claim_calls >= 1:
                    score += 2
                    findings.append(f"Outcome validation started: {claim_calls} operations")
                    recommendations.append("Register and verify more agent claims")
                else:
                    findings.append("No outcome validation detected")
                    recommendations.append("Use register_claim + verify_claim to prove AI outcomes")

                # Actual verification data (8 pts)
                try:
                    cur.execute(
                        """
                        SELECT
                            COUNT(*) AS total,
                            COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                            COUNT(*) FILTER (WHERE status = 'failed') AS failed
                        FROM outcome_claims
                        WHERE api_key_hash = %s
                          AND claimed_at >= NOW() - INTERVAL '30 days'
                        """,
                        (key_hash,),
                    )
                    row = cur.fetchone()
                    total = row["total"] if row else 0
                    verified = row["verified"] if row else 0
                    failed = row["failed"] if row else 0
                    decidable = verified + failed

                    if total >= 10 and decidable > 0:
                        rate = verified / decidable * 100
                        if rate >= 90:
                            score += 8
                            findings.append(f"Excellent verification rate: {rate:.0f}% ({verified}/{decidable})")
                        elif rate >= 70:
                            score += 6
                            findings.append(f"Good verification rate: {rate:.0f}% ({verified}/{decidable})")
                        elif rate >= 50:
                            score += 4
                            findings.append(f"Moderate verification rate: {rate:.0f}% ({verified}/{decidable})")
                            recommendations.append("Improve agent reliability to increase verification rate")
                        else:
                            score += 2
                            findings.append(f"Low verification rate: {rate:.0f}% ({verified}/{decidable})")
                            recommendations.append("Investigate failing claims — agents may need fixes")
                    elif total >= 1:
                        score += 3
                        findings.append(f"Outcome tracking started: {total} claims")
                        recommendations.append("Increase claim volume for meaningful verification metrics")
                    else:
                        recommendations.append("Start tracking agent outcomes with register_claim")
                except Exception:
                    pass  # outcome_claims table may not exist yet

                score = min(score, 14)

    except Exception:
        findings.append("Unable to assess outcome validation")

    return {"score": score, "max": 14, "findings": findings, "recommendations": recommendations}


def _score_observability(key_hash: str) -> Dict[str, Any]:
    """Observability: traces, events, dashboard usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                trace_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_start_trace", "thinkneo_end_trace",
                    "thinkneo_log_event", "thinkneo_get_trace",
                ])
                dashboard_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_get_observability_dashboard",
                ])

                # Trace usage (7 pts)
                if trace_calls >= 20:
                    score += 7
                    findings.append(f"Active agent tracing: {trace_calls} trace operations")
                elif trace_calls >= 5:
                    score += 5
                    findings.append(f"Good tracing coverage: {trace_calls} operations")
                elif trace_calls >= 1:
                    score += 2
                    findings.append(f"Tracing started: {trace_calls} operations")
                    recommendations.append("Trace all agent sessions for full observability")
                else:
                    findings.append("No agent tracing detected")
                    recommendations.append("Use start_trace/log_event/end_trace for agent observability")

                # Dashboard monitoring (3 pts)
                if dashboard_calls >= 5:
                    score += 3
                    findings.append(f"Active dashboard monitoring: {dashboard_calls} views")
                elif dashboard_calls >= 1:
                    score += 2
                    findings.append(f"Dashboard used: {dashboard_calls} views")
                else:
                    recommendations.append("Monitor agent health via observability dashboard")

                # Actual session data (2 pts)
                try:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM agent_sessions
                        WHERE api_key_hash = %s
                          AND started_at >= NOW() - INTERVAL '30 days'
                        """,
                        (key_hash,),
                    )
                    row = cur.fetchone()
                    sessions = row["cnt"] if row else 0
                    if sessions >= 5:
                        score += 2
                        findings.append(f"Active sessions tracked: {sessions}")
                    elif sessions >= 1:
                        score += 1
                        findings.append(f"Sessions tracked: {sessions}")
                except Exception:
                    pass

                score = min(score, 12)

    except Exception:
        findings.append("Unable to assess observability")

    return {"score": score, "max": 12, "findings": findings, "recommendations": recommendations}


def _score_smart_routing(key_hash: str) -> Dict[str, Any]:
    """Smart Routing: cost optimization through intelligent model selection."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                routing_calls = _count_tool_calls(cur, key_hash, [
                    "thinkneo_route_model", "thinkneo_get_savings_report",
                    "thinkneo_simulate_savings",
                ])

                if routing_calls >= 10:
                    score += 4
                    findings.append(f"Active smart routing: {routing_calls} routing operations")
                elif routing_calls >= 3:
                    score += 3
                    findings.append(f"Good routing usage: {routing_calls} operations")
                elif routing_calls >= 1:
                    score += 1
                    findings.append(f"Routing started: {routing_calls} operations")
                    recommendations.append("Route more requests through Smart Router for cost savings")
                else:
                    findings.append("No smart routing detected")
                    recommendations.append("Use Smart Router to optimize AI costs by 40-80%")

                # Check actual savings data
                try:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt,
                               COALESCE(SUM(savings), 0) AS total_savings
                        FROM router_requests
                        WHERE key_hash = %s
                          AND routed_at >= NOW() - INTERVAL '30 days'
                        """,
                        (key_hash,),
                    )
                    row = cur.fetchone()
                    requests = row["cnt"] if row else 0
                    savings = float(row["total_savings"]) if row else 0

                    if requests >= 5 and savings > 0:
                        score += 2
                        findings.append(f"Cost savings achieved: ${savings:.4f} across {requests} requests")
                    elif requests >= 1:
                        score += 1
                        findings.append(f"Routing active: {requests} requests logged")
                except Exception:
                    pass

                score = min(score, 6)

    except Exception:
        findings.append("Unable to assess smart routing")

    return {"score": score, "max": 6, "findings": findings, "recommendations": recommendations}


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _generate_report_token() -> str:
    """Generate a URL-safe report token."""
    return secrets.token_urlsafe(24)


def _store_trust_score(
    key_hash: str,
    org_name: str,
    score: int,
    breakdown: Dict[str, Any],
    badge: str,
    report_token: str,
) -> None:
    """Store the trust score evaluation in the database."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trust_scores
                        (api_key_hash, org_name, score, breakdown, badge_level, evaluated_at, valid_until, report_token)
                    VALUES
                        (%s, %s, %s, %s, %s, NOW(), NOW() + INTERVAL '30 days', %s)
                    """,
                    (key_hash, org_name, score, json.dumps(breakdown), badge, report_token),
                )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to store trust score: %s", exc)


def _get_latest_trust_score(key_hash: str) -> Optional[Dict[str, Any]]:
    """Get the latest valid trust score for an API key."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM trust_scores
                    WHERE api_key_hash = %s AND valid_until > NOW()
                    ORDER BY evaluated_at DESC
                    LIMIT 1
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception:
        return None


def get_trust_badge_by_token(report_token: str) -> Optional[Dict[str, Any]]:
    """Get trust score by public report token. Used by badge endpoint."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT org_name, score, badge_level, evaluated_at, valid_until
                    FROM trust_scores
                    WHERE report_token = %s AND valid_until > NOW()
                    ORDER BY evaluated_at DESC
                    LIMIT 1
                    """,
                    (report_token,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="thinkneo_evaluate_trust_score",
        description=(
            "Evaluate your organization AI Trust Score (0-100) across 10 dimensions: "
            "Guardrails, PII Protection, Injection Defense, Audit Trail, Compliance, "
            "Model Governance, Cost Controls, Outcome Validation, Observability, and Smart Routing. "
            "Returns a score, detailed breakdown, badge level (Platinum/Gold/Silver/Bronze/Unrated), "
            "and actionable recommendations. Score is valid for 30 days. "
            "Generates a public badge URL for embedding in websites and documentation. "
            "Part of the 'From Prompt to Proof' framework. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_evaluate_trust_score(
        org_name: Annotated[str, Field(description="Organization name for the trust score badge (e.g., 'Acme Corp')")],
    ) -> str:
        require_auth()

        token = get_bearer_token()
        key_h = hash_key(token)

        # Run all 10 scoring categories
        guardrails = _score_guardrails(key_h)
        pii = _score_pii_protection(key_h)
        injection = _score_injection_defense(key_h)
        audit = _score_audit_trail(key_h)
        compliance = _score_compliance(key_h)
        model_gov = _score_model_governance(key_h)
        cost = _score_cost_controls(key_h)
        outcome = _score_outcome_validation(key_h)
        observability = _score_observability(key_h)
        routing = _score_smart_routing(key_h)

        # Calculate total
        total_score = (
            guardrails["score"]
            + pii["score"]
            + injection["score"]
            + audit["score"]
            + compliance["score"]
            + model_gov["score"]
            + cost["score"]
            + outcome["score"]
            + observability["score"]
            + routing["score"]
        )
        total_score = min(total_score, 100)

        badge = _badge_level(total_score)
        report_token = _generate_report_token()

        breakdown = {
            "guardrails": guardrails,
            "pii_protection": pii,
            "injection_defense": injection,
            "audit_trail": audit,
            "compliance": compliance,
            "model_governance": model_gov,
            "cost_controls": cost,
            "outcome_validation": outcome,
            "observability": observability,
            "smart_routing": routing,
        }

        # Store in database
        _store_trust_score(key_h, org_name, total_score, breakdown, badge, report_token)

        # Collect all recommendations
        all_recommendations = []
        for cat in breakdown.values():
            all_recommendations.extend(cat.get("recommendations", []))

        result = {
            "org_name": org_name,
            "trust_score": total_score,
            "max_score": 100,
            "badge_level": badge,
            "badge_label": BADGE_LABELS[badge],
            "breakdown": {
                k: {"score": v["score"], "max": v["max"], "findings": v["findings"]}
                for k, v in breakdown.items()
            },
            "top_recommendations": all_recommendations[:10],
            "report_token": report_token,
            "badge_url": f"https://mcp.thinkneo.ai/badge/{report_token}",
            "badge_json_url": f"https://mcp.thinkneo.ai/badge/{report_token}.json",
            "badge_markdown": f"[![ThinkNEO Trust Score](https://mcp.thinkneo.ai/badge/{report_token})](https://thinkneo.ai/trust)",
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
            "evaluated_at": utcnow(),
            "note": (
                "Score reflects governance tool usage and outcome verification over the last 30 days. "
                "10 categories across the full 'From Prompt to Proof' framework. "
                "Re-evaluate anytime to update your score."
            ),
            "trust_center": "https://thinkneo.ai/trust",
        }

        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_get_trust_badge",
        description=(
            "Get a public AI Trust Score badge by report token. "
            "Returns the organization name, score, badge level, and validity period. "
            "Use the badge URL to embed the trust badge in websites and documentation. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_get_trust_badge(
        report_token: Annotated[str, Field(description="The report token from a trust score evaluation (URL-safe string)")],
    ) -> str:
        badge_data = get_trust_badge_by_token(report_token)

        if not badge_data:
            return json.dumps({
                "error": "badge_not_found",
                "message": "No valid trust score found for this token. The score may have expired or the token is invalid.",
                "help": "Run thinkneo_evaluate_trust_score to generate a new trust score.",
            }, indent=2)

        result = {
            "org_name": badge_data["org_name"],
            "trust_score": badge_data["score"],
            "badge_level": badge_data["badge_level"],
            "badge_label": BADGE_LABELS.get(badge_data["badge_level"], "Unknown"),
            "evaluated_at": badge_data["evaluated_at"].isoformat().replace("+00:00", "Z") if badge_data["evaluated_at"] else None,
            "valid_until": badge_data["valid_until"].isoformat().replace("+00:00", "Z") if badge_data["valid_until"] else None,
            "badge_url": f"https://mcp.thinkneo.ai/badge/{report_token}",
            "badge_svg_url": f"https://mcp.thinkneo.ai/badge/{report_token}",
            "badge_json_url": f"https://mcp.thinkneo.ai/badge/{report_token}.json",
            "embed_markdown": f"[![ThinkNEO Trust Score](https://mcp.thinkneo.ai/badge/{report_token})](https://thinkneo.ai/trust)",
            "trust_center": "https://thinkneo.ai/trust",
        }

        return json.dumps(result, indent=2, ensure_ascii=False)
