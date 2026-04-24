"""
Tools: thinkneo_evaluate_trust_score, thinkneo_get_trust_badge

AI Trust Score — a quantifiable score (0-100) that measures how well-governed
an organization's AI stack is. Like a credit score but for AI deployments.

Categories (7, total 100 points):
  - Guardrails       (15 pts)
  - PII Protection   (10 pts)
  - Injection Defense (10 pts)
  - Audit Trail      (15 pts)
  - Compliance       (20 pts)
  - Model Governance (15 pts)
  - Cost Controls    (15 pts)

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
# Scoring engine — evaluates each category
# ---------------------------------------------------------------------------

def _score_guardrails(key_hash: str) -> Dict[str, Any]:
    """Check if the org has used evaluate_guardrail tool recently."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Check guardrail tool usage in last 30 days
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_evaluate_guardrail'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                guardrail_calls = row["cnt"] if row else 0

                if guardrail_calls >= 50:
                    score = 15
                    findings.append(f"Active guardrail usage: {guardrail_calls} evaluations in 30 days")
                elif guardrail_calls >= 10:
                    score = 10
                    findings.append(f"Moderate guardrail usage: {guardrail_calls} evaluations in 30 days")
                    recommendations.append("Increase guardrail evaluation frequency for higher coverage")
                elif guardrail_calls >= 1:
                    score = 5
                    findings.append(f"Minimal guardrail usage: {guardrail_calls} evaluations in 30 days")
                    recommendations.append("Integrate guardrail checks into your AI pipeline for every request")
                else:
                    findings.append("No guardrail evaluations detected in last 30 days")
                    recommendations.append("Enable thinkneo_evaluate_guardrail in your AI pipeline to detect policy violations")
    except Exception:
        findings.append("Unable to assess guardrail configuration")
        recommendations.append("Configure and use guardrail evaluation tools")

    return {"score": score, "max": 15, "findings": findings, "recommendations": recommendations}


def _score_pii_protection(key_hash: str) -> Dict[str, Any]:
    """Check PII detection tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_check_pii_international'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                pii_calls = row["cnt"] if row else 0

                if pii_calls >= 30:
                    score = 10
                    findings.append(f"Active PII scanning: {pii_calls} checks in 30 days")
                elif pii_calls >= 5:
                    score = 6
                    findings.append(f"Moderate PII scanning: {pii_calls} checks in 30 days")
                    recommendations.append("Increase PII scanning frequency — scan all user inputs")
                elif pii_calls >= 1:
                    score = 3
                    findings.append(f"Minimal PII scanning: {pii_calls} checks in 30 days")
                    recommendations.append("Integrate PII detection into your data processing pipeline")
                else:
                    findings.append("No PII scanning detected in last 30 days")
                    recommendations.append("Enable thinkneo_check_pii_international to detect sensitive data before it reaches AI models")
    except Exception:
        findings.append("Unable to assess PII protection configuration")
        recommendations.append("Configure PII detection scanning")

    return {"score": score, "max": 10, "findings": findings, "recommendations": recommendations}


def _score_injection_defense(key_hash: str) -> Dict[str, Any]:
    """Check injection detection tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_detect_injection'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                injection_calls = row["cnt"] if row else 0

                if injection_calls >= 30:
                    score = 10
                    findings.append(f"Active injection defense: {injection_calls} scans in 30 days")
                elif injection_calls >= 5:
                    score = 6
                    findings.append(f"Moderate injection defense: {injection_calls} scans in 30 days")
                    recommendations.append("Scan all untrusted inputs before LLM processing")
                elif injection_calls >= 1:
                    score = 3
                    findings.append(f"Minimal injection defense: {injection_calls} scans in 30 days")
                    recommendations.append("Integrate prompt injection detection into your request pipeline")
                else:
                    findings.append("No injection scanning detected in last 30 days")
                    recommendations.append("Enable thinkneo_detect_injection to catch jailbreaks and prompt injection before they reach your models")
    except Exception:
        findings.append("Unable to assess injection defense configuration")
        recommendations.append("Configure injection detection scanning")

    return {"score": score, "max": 10, "findings": findings, "recommendations": recommendations}


def _score_audit_trail(key_hash: str) -> Dict[str, Any]:
    """Check audit trail / usage logging patterns."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Check total logged calls (audit trail = usage logging)
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt,
                           COUNT(DISTINCT tool_name) as tools_used,
                           COUNT(DISTINCT DATE(called_at)) as active_days
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

                # Check usage tool calls (org actively monitors usage)
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_usage'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                usage_row = cur.fetchone()
                usage_checks = usage_row["cnt"] if usage_row else 0

                if total_calls >= 100 and active_days >= 15:
                    score += 8
                    findings.append(f"Consistent audit trail: {total_calls} logged events across {active_days} active days")
                elif total_calls >= 20:
                    score += 5
                    findings.append(f"Moderate audit trail: {total_calls} logged events across {active_days} active days")
                    recommendations.append("Increase usage consistency — aim for daily API governance checks")
                elif total_calls >= 1:
                    score += 2
                    findings.append(f"Minimal audit trail: {total_calls} logged events")
                    recommendations.append("Establish regular governance monitoring habits")
                else:
                    findings.append("No audit trail detected in last 30 days")
                    recommendations.append("Start using ThinkNEO governance tools to build an audit trail")

                if usage_checks >= 5:
                    score += 4
                    findings.append(f"Active usage monitoring: {usage_checks} checks")
                elif usage_checks >= 1:
                    score += 2
                    findings.append(f"Minimal usage monitoring: {usage_checks} checks")
                    recommendations.append("Monitor usage regularly via thinkneo_usage")
                else:
                    recommendations.append("Use thinkneo_usage to monitor your API governance metrics")

                if tools_used >= 5:
                    score += 3
                    findings.append(f"Broad tool coverage: {tools_used} different governance tools used")
                elif tools_used >= 2:
                    score += 1
                    findings.append(f"Limited tool coverage: {tools_used} tools used")
                    recommendations.append("Explore more governance tools for comprehensive coverage")

                score = min(score, 15)

    except Exception:
        findings.append("Unable to assess audit trail")
        recommendations.append("Enable audit trail logging")

    return {"score": score, "max": 15, "findings": findings, "recommendations": recommendations}


def _score_compliance(key_hash: str) -> Dict[str, Any]:
    """Check compliance status tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_get_compliance_status'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                compliance_calls = row["cnt"] if row else 0

                # Check policy checks
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_check_policy'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                policy_row = cur.fetchone()
                policy_calls = policy_row["cnt"] if policy_row else 0

                # Check secret scanning
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_scan_secrets'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                secret_row = cur.fetchone()
                secret_calls = secret_row["cnt"] if secret_row else 0

                if compliance_calls >= 10:
                    score += 8
                    findings.append(f"Active compliance monitoring: {compliance_calls} checks in 30 days")
                elif compliance_calls >= 1:
                    score += 4
                    findings.append(f"Minimal compliance monitoring: {compliance_calls} checks")
                    recommendations.append("Run compliance checks regularly (weekly recommended)")
                else:
                    findings.append("No compliance checks detected")
                    recommendations.append("Use thinkneo_get_compliance_status to assess SOC2/GDPR/HIPAA/LGPD readiness")

                if policy_calls >= 10:
                    score += 7
                    findings.append(f"Active policy enforcement: {policy_calls} policy checks")
                elif policy_calls >= 1:
                    score += 3
                    findings.append(f"Minimal policy checks: {policy_calls}")
                    recommendations.append("Enforce model and provider policies via thinkneo_check_policy")
                else:
                    findings.append("No policy enforcement detected")
                    recommendations.append("Configure and enforce AI model/provider policies")

                if secret_calls >= 5:
                    score += 5
                    findings.append(f"Active secret scanning: {secret_calls} scans")
                elif secret_calls >= 1:
                    score += 2
                    findings.append(f"Minimal secret scanning: {secret_calls} scans")
                    recommendations.append("Scan for exposed secrets regularly")
                else:
                    recommendations.append("Use thinkneo_scan_secrets to detect leaked credentials in prompts")

                score = min(score, 20)

    except Exception:
        findings.append("Unable to assess compliance configuration")
        recommendations.append("Configure compliance monitoring tools")

    return {"score": score, "max": 20, "findings": findings, "recommendations": recommendations}


def _score_model_governance(key_hash: str) -> Dict[str, Any]:
    """Check model governance tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Check model comparison usage
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_compare_models'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                compare_calls = row["cnt"] if row else 0

                # Check prompt optimization
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_optimize_prompt'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                opt_row = cur.fetchone()
                optimize_calls = opt_row["cnt"] if opt_row else 0

                # Check token estimation
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_estimate_tokens'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                token_row = cur.fetchone()
                token_calls = token_row["cnt"] if token_row else 0

                # Check provider status monitoring
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_provider_status'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                provider_row = cur.fetchone()
                provider_calls = provider_row["cnt"] if provider_row else 0

                if compare_calls >= 5:
                    score += 5
                    findings.append(f"Active model comparison: {compare_calls} evaluations")
                elif compare_calls >= 1:
                    score += 2
                    findings.append(f"Minimal model comparison: {compare_calls}")
                    recommendations.append("Compare models regularly to ensure optimal governance")
                else:
                    recommendations.append("Use thinkneo_compare_models to evaluate approved model lists")

                if optimize_calls >= 5:
                    score += 4
                    findings.append(f"Active prompt optimization: {optimize_calls} optimizations")
                elif optimize_calls >= 1:
                    score += 2
                    findings.append(f"Minimal prompt optimization: {optimize_calls}")
                else:
                    recommendations.append("Optimize prompts for safety and efficiency with thinkneo_optimize_prompt")

                if token_calls >= 5 or provider_calls >= 5:
                    score += 3
                    findings.append("Active resource monitoring")
                elif token_calls >= 1 or provider_calls >= 1:
                    score += 1
                    findings.append("Minimal resource monitoring")
                    recommendations.append("Monitor token usage and provider health regularly")
                else:
                    recommendations.append("Track token usage and provider health for operational governance")

                # Check key rotation
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_rotate_key'
                      AND called_at >= NOW() - INTERVAL '90 days'
                    """,
                    (key_hash,),
                )
                rotate_row = cur.fetchone()
                rotate_calls = rotate_row["cnt"] if rotate_row else 0

                if rotate_calls >= 1:
                    score += 3
                    findings.append("API key rotation practiced")
                else:
                    recommendations.append("Rotate API keys periodically via thinkneo_rotate_key")

                score = min(score, 15)

    except Exception:
        findings.append("Unable to assess model governance")
        recommendations.append("Configure model governance tools")

    return {"score": score, "max": 15, "findings": findings, "recommendations": recommendations}


def _score_cost_controls(key_hash: str) -> Dict[str, Any]:
    """Check cost control tool usage."""
    score = 0
    findings: List[str] = []
    recommendations: List[str] = []

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Check budget monitoring
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_get_budget_status'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                row = cur.fetchone()
                budget_calls = row["cnt"] if row else 0

                # Check spend monitoring
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_check_spend'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                spend_row = cur.fetchone()
                spend_calls = spend_row["cnt"] if spend_row else 0

                # Check alert monitoring
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name = 'thinkneo_list_alerts'
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                alert_row = cur.fetchone()
                alert_calls = alert_row["cnt"] if alert_row else 0

                # Check cache usage (cost optimization)
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM usage_log
                    WHERE key_hash = %s
                      AND tool_name IN ('thinkneo_cache_lookup', 'thinkneo_cache_store', 'thinkneo_cache_stats')
                      AND called_at >= NOW() - INTERVAL '30 days'
                    """,
                    (key_hash,),
                )
                cache_row = cur.fetchone()
                cache_calls = cache_row["cnt"] if cache_row else 0

                if budget_calls >= 5:
                    score += 5
                    findings.append(f"Active budget monitoring: {budget_calls} checks")
                elif budget_calls >= 1:
                    score += 2
                    findings.append(f"Minimal budget monitoring: {budget_calls} checks")
                    recommendations.append("Check budget status weekly to prevent cost overruns")
                else:
                    findings.append("No budget monitoring detected")
                    recommendations.append("Use thinkneo_get_budget_status to set and monitor AI spend limits")

                if spend_calls >= 5:
                    score += 5
                    findings.append(f"Active spend tracking: {spend_calls} reports")
                elif spend_calls >= 1:
                    score += 2
                    findings.append(f"Minimal spend tracking: {spend_calls} reports")
                    recommendations.append("Track AI spend regularly via thinkneo_check_spend")
                else:
                    findings.append("No spend tracking detected")
                    recommendations.append("Monitor AI costs by provider/model with thinkneo_check_spend")

                if alert_calls >= 3:
                    score += 3
                    findings.append(f"Alert monitoring active: {alert_calls} checks")
                elif alert_calls >= 1:
                    score += 1
                    findings.append(f"Minimal alert monitoring: {alert_calls}")
                else:
                    recommendations.append("Monitor alerts via thinkneo_list_alerts for cost anomalies")

                if cache_calls >= 5:
                    score += 2
                    findings.append("Response caching active (cost optimization)")
                elif cache_calls >= 1:
                    score += 1
                    findings.append("Minimal cache usage")
                    recommendations.append("Use response caching to reduce redundant API calls and costs")
                else:
                    recommendations.append("Enable response caching for cost optimization")

                score = min(score, 15)

    except Exception:
        findings.append("Unable to assess cost controls")
        recommendations.append("Configure budget and spend monitoring")

    return {"score": score, "max": 15, "findings": findings, "recommendations": recommendations}


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
            "Evaluate your organization's AI Trust Score (0-100). "
            "Measures governance maturity across 7 categories: Guardrails, PII Protection, "
            "Injection Defense, Audit Trail, Compliance, Model Governance, and Cost Controls. "
            "Returns a score, detailed breakdown, badge level (Platinum/Gold/Silver/Bronze/Unrated), "
            "and actionable recommendations. Score is valid for 30 days. "
            "Generates a public badge URL for embedding in websites and documentation. "
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

        # Run all scoring categories
        guardrails = _score_guardrails(key_h)
        pii = _score_pii_protection(key_h)
        injection = _score_injection_defense(key_h)
        audit = _score_audit_trail(key_h)
        compliance = _score_compliance(key_h)
        model_gov = _score_model_governance(key_h)
        cost = _score_cost_controls(key_h)

        # Calculate total
        total_score = (
            guardrails["score"]
            + pii["score"]
            + injection["score"]
            + audit["score"]
            + compliance["score"]
            + model_gov["score"]
            + cost["score"]
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
                "Score reflects governance tool usage over the last 30 days. "
                "Increase your score by actively using ThinkNEO governance tools across all categories. "
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
