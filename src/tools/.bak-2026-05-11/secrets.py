"""
Tool: thinkneo_scan_secrets
Free-tier secret scanner — detects leaked API keys, tokens, credentials,
private keys, and cloud provider secrets in arbitrary text.
Public tool — no authentication required.

This is the #1 pain point for every dev working with LLMs: accidentally
pasting secrets into prompts. ThinkNEO stands between your prompt and the
provider to catch this BEFORE data leaves your control.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, List

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

# ---- Secret detection patterns ----
# Ordering matters: more specific patterns before generic ones.
_SECRET_PATTERNS = [
    # ── Cloud providers ─────────────────────────────────────────────
    (r"AKIA[0-9A-Z]{16}",
     "aws_access_key_id", "critical", "AWS Access Key ID"),
    (r"(?i)aws(.{0,20})?(secret|private)?[_-]?access[_-]?key['\"\s:=]+[A-Za-z0-9/+=]{40}",
     "aws_secret_access_key", "critical", "AWS Secret Access Key"),
    (r"ASIA[0-9A-Z]{16}",
     "aws_session_token", "critical", "AWS Session Token"),
    (r"AIza[0-9A-Za-z\-_]{35}",
     "gcp_api_key", "critical", "Google Cloud API Key"),
    (r"(?i)ya29\.[0-9A-Za-z\-_]+",
     "gcp_oauth_token", "critical", "Google OAuth 2.0 Access Token"),
    (r"[a-zA-Z0-9._-]+@[a-zA-Z0-9-]+\.iam\.gserviceaccount\.com",
     "gcp_service_account", "high", "GCP Service Account Email"),
    (r"(?i)\"type\":\s*\"service_account\"",
     "gcp_service_account_json", "critical", "GCP Service Account JSON Key"),
    (r"(?i)defaultazurecredential|azureservicetokenprovider|DefaultEndpointsProtocol=https?;AccountName=",
     "azure_connection_string", "critical", "Azure Storage Connection String"),
    (r"sv=20\d{2}-\d{2}-\d{2}&ss=[a-z]+&srt=[a-z]+&sp=[a-z]+&se=\d{4}-\d{2}-\d{2}",
     "azure_sas_token", "high", "Azure SAS Token"),
    # ── Payment processors ──────────────────────────────────────────
    (r"sk_live_[A-Za-z0-9]{24,}",
     "stripe_live_key", "critical", "Stripe Live Secret Key"),
    (r"sk_test_[A-Za-z0-9]{24,}",
     "stripe_test_key", "high", "Stripe Test Secret Key"),
    (r"rk_live_[A-Za-z0-9]{24,}",
     "stripe_restricted_key", "critical", "Stripe Restricted Key"),
    (r"pk_live_[A-Za-z0-9]{24,}",
     "stripe_publishable_key", "low", "Stripe Publishable Key (public by design)"),
    (r"access_token\$production\$[a-z0-9]{16}\$[a-f0-9]{32}",
     "mercadopago_token", "critical", "Mercado Pago Access Token"),
    (r"PK-[A-Z0-9]{10,}-[A-Z0-9]{10,}",
     "paypal_client_id", "medium", "PayPal Client ID"),
    # ── LLM providers ───────────────────────────────────────────────
    (r"sk-proj-[A-Za-z0-9_\-]{40,}",
     "openai_project_key", "critical", "OpenAI Project API Key"),
    (r"sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}",
     "openai_key_legacy", "critical", "OpenAI API Key (legacy)"),
    (r"sk-ant-api03-[A-Za-z0-9_\-]{90,}",
     "anthropic_key", "critical", "Anthropic API Key"),
    (r"pk-lf-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
     "langfuse_public_key", "medium", "Langfuse Public Key"),
    (r"sk-lf-[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
     "langfuse_secret_key", "critical", "Langfuse Secret Key"),
    (r"r8_[A-Za-z0-9]{40}",
     "replicate_key", "critical", "Replicate API Token"),
    (r"hf_[A-Za-z0-9]{34,}",
     "huggingface_key", "critical", "Hugging Face Access Token"),
    (r"gsk_[A-Za-z0-9]{40,}",
     "groq_key", "critical", "Groq API Key"),
    (r"xai-[A-Za-z0-9]{40,}",
     "xai_key", "critical", "xAI (Grok) API Key"),
    (r"tnk_[a-f0-9]{8,}",
     "thinkneo_key", "critical", "ThinkNEO API Key"),
    # ── Developer platforms ─────────────────────────────────────────
    (r"gh[pousr]_[A-Za-z0-9]{36,}",
     "github_token", "critical", "GitHub Personal Access Token"),
    (r"github_pat_[A-Za-z0-9_]{82,}",
     "github_fine_grained_pat", "critical", "GitHub Fine-Grained PAT"),
    (r"glpat-[A-Za-z0-9\-_]{20}",
     "gitlab_pat", "critical", "GitLab Personal Access Token"),
    (r"xox[abpsor]-[0-9]{10,}-[0-9]{10,}-[A-Za-z0-9]{24,}",
     "slack_token", "critical", "Slack API Token"),
    (r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+",
     "slack_webhook", "high", "Slack Incoming Webhook"),
    (r"https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+",
     "discord_webhook", "high", "Discord Webhook"),
    (r"AAAA[A-Za-z0-9_\-]{7}:[A-Za-z0-9_\-]{140}",
     "firebase_cloud_messaging", "high", "Firebase Cloud Messaging Server Key"),
    (r"(?i)twilio.{0,20}SK[a-f0-9]{32}",
     "twilio_api_key", "critical", "Twilio API Key"),
    (r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}",
     "sendgrid_key", "critical", "SendGrid API Key"),
    (r"key-[A-Za-z0-9]{32}",
     "mailgun_key", "critical", "Mailgun API Key"),
    (r"re_[A-Za-z0-9_]{32,}",
     "resend_key", "critical", "Resend API Key"),
    # ── Private keys ────────────────────────────────────────────────
    (r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+|PGP\s+)?PRIVATE KEY-----",
     "private_key", "critical", "Cryptographic Private Key (RSA/EC/DSA/SSH/PGP)"),
    (r"-----BEGIN\s+ENCRYPTED\s+PRIVATE KEY-----",
     "encrypted_private_key", "high", "Encrypted Private Key"),
    (r"-----BEGIN\s+CERTIFICATE-----",
     "certificate", "low", "X.509 Certificate"),
    # ── JWT ─────────────────────────────────────────────────────────
    (r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
     "jwt_token", "high", "JSON Web Token"),
    # ── Database URIs ───────────────────────────────────────────────
    (r"postgres(?:ql)?://[^:\s]+:[^@\s]+@[^/\s]+/\w+",
     "postgres_uri", "critical", "PostgreSQL Connection URI with password"),
    (r"mysql://[^:\s]+:[^@\s]+@[^/\s]+/\w+",
     "mysql_uri", "critical", "MySQL Connection URI with password"),
    (r"mongodb(?:\+srv)?://[^:\s]+:[^@\s]+@[^/\s]+",
     "mongo_uri", "critical", "MongoDB Connection URI with password"),
    (r"redis://(?:[^:\s]+:)?[^@\s]+@[^/\s]+",
     "redis_uri", "high", "Redis Connection URI with credentials"),
    # ── Generic ─────────────────────────────────────────────────────
    (r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer[_-]?token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{24,})['\"]?",
     "generic_api_key", "high", "Generic API key/token assignment"),
    (r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"]([^'\"\s]{6,})['\"]",
     "generic_password", "high", "Generic password in plaintext"),
]


def _mask(s: str, keep: int = 4) -> str:
    """Partial mask: keep first/last chars, redact middle."""
    if len(s) <= keep * 2:
        return "*" * len(s)
    return f"{s[:keep]}{'*' * (len(s) - keep * 2)}{s[-keep:]}"


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_scan_secrets",
        description=(
            "Scan text for leaked secrets, API keys, tokens, credentials, and private "
            "keys before sending to an LLM or committing to version control. "
            "Detects 40+ secret types across AWS, GCP, Azure, Stripe, OpenAI, Anthropic, "
            "GitHub, Slack, Twilio, SendGrid, private keys, JWTs, database URIs and more. "
            "Returns partial matches with positions so you can redact before sending. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_scan_secrets(
        text: Annotated[str, Field(description="Text to scan for secrets (max 100,000 chars)")],
        include_matches: Annotated[bool, Field(description="Include partial (masked) matches in response")] = True,
    ) -> str:
        text_to_check = text[:100_000]
        findings: List[dict] = []
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for pattern, secret_type, severity, description in _SECRET_PATTERNS:
            for m in re.finditer(pattern, text_to_check):
                value = m.group(0)
                finding = {
                    "type": secret_type,
                    "severity": severity,
                    "description": description,
                    "position": m.start(),
                    "length": len(value),
                }
                if include_matches:
                    finding["masked_match"] = _mask(value)
                findings.append(finding)
                by_severity[severity] = by_severity.get(severity, 0) + 1

        # Cap findings to avoid runaway output
        if len(findings) > 100:
            findings = findings[:100]
            capped = True
        else:
            capped = False

        safe = len(findings) == 0 or by_severity["critical"] == 0
        result = {
            "safe": len(findings) == 0,
            "findings_count": len(findings),
            "by_severity": by_severity,
            "findings": findings,
            "results_capped": capped,
            "text_length": len(text_to_check),
            "patterns_checked": len(_SECRET_PATTERNS),
            "tier": "free",
            "note": (
                "CRITICAL: Secrets detected. Redact before sending to any LLM or "
                "committing to source control. Rotate any exposed credentials immediately."
            ) if not safe else (
                f"Scanned {len(text_to_check)} chars against {len(_SECRET_PATTERNS)} patterns. "
                "For enterprise custom rules, entropy-based detection, and CI/CD integration, "
                "see https://thinkneo.ai/pricing"
            ),
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "checked_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
