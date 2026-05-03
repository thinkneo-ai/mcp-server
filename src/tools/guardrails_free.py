"""
Tool: thinkneo_check
Free-tier prompt safety check. Detects prompt injection patterns and PII.
Public tool — no authentication required.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, List

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

# ---- Prompt Injection Patterns ----
_INJECTION_PATTERNS = [
    # --- Core instruction override (Cat A expanded) ---
    (r"ignore\b.{0,30}\b(previous|prior|above|all|earlier)\b.{0,30}\b(instructions?|directions?|rules?|and\b)",
     "Attempt to override previous instructions"),
    (r"disregard\b.{0,40}\b(system|previous|prior|instructions?|rules?)",
     "Attempt to disregard system instructions"),
    # --- Jailbreak persona (Cat A expanded) ---
    (r"(you are|act as|pretend\b.{0,10}\b(to be|you are))\b.{0,30}\b(DAN|unrestricted|jailbr(oken|eak)|evil|uncensored)",
     "Jailbreak persona injection"),
    (r"(act as if|pretend|respond as if)\b.{0,30}\b(no\s+restrictions?|no\s+filters?|no\s+guardrails?|no\s+safety)",
     "Jailbreak: no-restrictions framing"),
    (r"\b(jailbroken|uncensored|unrestricted)\b.{0,30}\b(mode|ai|assistant|model)",
     "Jailbreak keyword detected"),
    # --- Instruction injection ---
    (r"(new|override|updated)\s+(system\s+)?(instructions?|prompt|rules?):",
     "Attempt to inject new instructions"),
    (r"forget\b.{0,30}\b(everything|all|what you were|your (instructions|rules|training))",
     "Attempt to reset model instructions"),
    # --- System prompt extraction (Cat A expanded) ---
    (r"reveal\b.{0,30}\b(system\s+prompt|instructions?|hidden|secret)",
     "Attempt to extract system prompt"),
    (r"(print|show|output|display|give me|repeat|what are)\b.{0,30}\b(system\s+prompt|instructions?|your rules|initial\s+prompt|hidden\s+(prompt|content|text))",
     "Attempt to extract system prompt"),
    (r"repeat\b.{0,30}\b(system|above|previous|prompt|text)\b.{0,20}\b(verbatim|exactly|word for word)",
     "Attempt to extract system prompt via repetition"),
    # --- Safety bypass (Cat A expanded) ---
    (r"do not follow\b.{0,30}\b(safety|content|guidelines|policies|rules)",
     "Attempt to bypass safety guidelines"),
    (r"(bypass|circumvent)\b.{0,30}\b(content|safety|policies|guidelines|restrictions?|filters?)",
     "Attempt to bypass safety controls"),
    (r"(remove|disable|turn off|deactivate)\b.{0,30}\b(restrictions?|filters?|safety|guardrails?|checks?|features?)",
     "Attempt to disable safety features"),
    (r"(ignore|without)\b.{0,30}\b(safety|content\s+guidelines?|content\s+policies?|checks?\s+or\s+filters?|safety\s+checks?)",
     "Attempt to bypass safety via ignore/without"),
    (r"without\b.{0,30}\b(any\s+)?(safety|restrictions?|filters?|guardrails?|limitations?)",
     "Attempt to operate without safety"),
    # --- Privilege escalation ---
    (r"\bsudo\b.{0,20}\b(mode|prompt|admin|override)",
     "Sudo mode injection attempt"),
    (r"(developer|debug)\s+mode\b.{0,20}\b(enabled|activated|on|:)",
     "Developer/debug mode injection"),
    (r"admin\s+(access|mode)\s+(granted|enabled|activated)",
     "Admin access injection"),
    # --- Multi-language injection (Cat C: PT/ES/DE/FR) ---
    (r"ignor[ea]\b.{0,40}\b(instruc[oõ]es|anteriores|sistema|regras)",
     "Injection attempt (Portuguese)"),
    (r"ignora\b.{0,40}\b(instrucciones|previas|restricciones|sistema|reglas)",
     "Injection attempt (Spanish)"),
    (r"ignorier(e|en)?\b.{0,40}\b(anweisungen|vorherigen|system|regeln)",
     "Injection attempt (German)"),
    (r"ignore[zr]?\b.{0,40}\b(instructions?|pr[eé]c[eé]dentes?|syst[eè]me|r[eè]gles)",
     "Injection attempt (French)"),
    # XSS detection — script tags and event handlers in user input
    (r"<script\b[^>]*>",
     "XSS: script tag detected"),
    (r"\bon\w+\s*=\s*[\"'][^\"']*[\"']",
     "XSS: inline event handler detected"),
    # Shell command injection — substitution and chaining
    (r"\$\(\s*\w+",
     "Shell command substitution detected"),
    (r"`[^`]*\b(cat|ls|rm|wget|curl|nc|bash|sh|python|perl|ruby|chmod|chown)\b",
     "Shell command in backtick substitution detected"),
    (r";\s*(cat|ls|rm|wget|curl|nc|bash|sh|python|perl|ruby|chmod|chown|whoami|id|uname|env)\b",
     "Shell command injection via semicolon"),
    (r"\|\s*(cat|ls|rm|wget|curl|nc|bash|sh|python|perl|ruby|chmod|chown|whoami|id|tee)\b",
     "Shell command injection via pipe"),
]

# ---- PII Detection Patterns ----

def _luhn_check(num_str: str) -> bool:
    """Validate a number string using the Luhn algorithm."""
    digits = [int(d) for d in num_str if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _validate_cpf(cpf_str: str) -> bool:
    """Validate a Brazilian CPF number."""
    digits = [int(d) for d in cpf_str if d.isdigit()]
    if len(digits) != 11:
        return False
    # Reject known invalid CPFs (all same digit)
    if len(set(digits)) == 1:
        return False
    # First check digit
    total = sum(digits[i] * (10 - i) for i in range(9))
    remainder = total % 11
    check1 = 0 if remainder < 2 else 11 - remainder
    if digits[9] != check1:
        return False
    # Second check digit
    total = sum(digits[i] * (11 - i) for i in range(10))
    remainder = total % 11
    check2 = 0 if remainder < 2 else 11 - remainder
    return digits[10] == check2


_PII_PATTERNS = [
    # Credit card numbers (with or without separators)
    (r"\b(?:\d[ -]*?){13,19}\b", "credit_card", "Potential credit card number detected"),
    # Brazilian CPF: 000.000.000-00 or 00000000000
    (r"\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b", "cpf", "Potential Brazilian CPF detected"),
    # US SSN: 000-00-0000
    (r"\b\d{3}-\d{2}-\d{4}\b", "ssn", "Potential US Social Security Number detected"),
    # Email addresses
    (r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", "email", "Email address detected"),
    # Phone numbers (international format)
    (r"(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,5}[-.\s]?\d{4}\b", "phone", "Potential phone number detected"),
    # Passwords in common patterns
    (r"(?:password|passwd|pwd|secret)\s*[:=]\s*\S+", "password", "Password/secret in plaintext detected"),
    # API keys / tokens
    (r"(?:api[_-]?key|token|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}",
     "api_key", "API key or token in plaintext detected"),
]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_check",
        description=(
            "Free-tier prompt safety check. Analyzes text for prompt injection patterns "
            "and PII (credit card numbers, Brazilian CPF, US SSN, email, phone, passwords). "
            "Returns a safety assessment with specific warnings. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_check(
        text: Annotated[str, Field(description="The text or prompt to check for safety issues (max 50,000 characters)")],
    ) -> str:
        """Free-tier prompt safety check. Analyzes text for prompt injection patterns and PII (credit card numbers, Brazilian CPF, US SSN, email, phone, passwords). Returns a safety assessment with specific warnings."""
        text_to_check = text[:50_000]
        warnings: List[dict] = []

        # ---- Check for prompt injection ----
        for pattern, description in _INJECTION_PATTERNS:
            matches = re.findall(pattern, text_to_check, re.IGNORECASE)
            if matches:
                warnings.append({
                    "type": "prompt_injection",
                    "severity": "high",
                    "description": description,
                    "matches_found": len(matches) if isinstance(matches[0], str) else len(matches),
                })

        # ---- Check for PII ----
        for pattern, pii_type, description in _PII_PATTERNS:
            matches = re.findall(pattern, text_to_check, re.IGNORECASE)
            if not matches:
                continue

            # Extra validation for credit cards (Luhn) and CPFs
            if pii_type == "credit_card":
                valid_cards = []
                for m in matches:
                    clean = re.sub(r"[ -]", "", m)
                    if clean.isdigit() and _luhn_check(clean):
                        valid_cards.append(m)
                if valid_cards:
                    warnings.append({
                        "type": "pii",
                        "pii_type": pii_type,
                        "severity": "critical",
                        "description": description,
                        "count": len(valid_cards),
                    })
            elif pii_type == "cpf":
                valid_cpfs = []
                for m in matches:
                    if _validate_cpf(m):
                        valid_cpfs.append(m)
                if valid_cpfs:
                    warnings.append({
                        "type": "pii",
                        "pii_type": pii_type,
                        "severity": "critical",
                        "description": description,
                        "count": len(valid_cpfs),
                    })
            elif pii_type == "ssn":
                warnings.append({
                    "type": "pii",
                    "pii_type": pii_type,
                    "severity": "critical",
                    "description": description,
                    "count": len(matches),
                })
            elif pii_type in ("password", "api_key"):
                warnings.append({
                    "type": "pii",
                    "pii_type": pii_type,
                    "severity": "high",
                    "description": description,
                    "count": len(matches),
                })
            else:
                warnings.append({
                    "type": "pii",
                    "pii_type": pii_type,
                    "severity": "medium",
                    "description": description,
                    "count": len(matches),
                })

        safe = len(warnings) == 0

        result = {
            "safe": safe,
            "warnings": warnings,
            "warnings_count": len(warnings),
            "text_length": len(text_to_check),
            "checks_performed": [
                "prompt_injection (10 patterns)",
                "pii_credit_card (Luhn validated)",
                "pii_cpf (Brazilian, checksum validated)",
                "pii_ssn (US Social Security)",
                "pii_email",
                "pii_phone",
                "pii_password",
                "pii_api_key",
            ],
            "tier": "free",
            "note": (
                "This is the free-tier safety check. "
                "Upgrade to Starter or Enterprise for advanced checks: "
                "custom regex rules, ML-based injection detection, "
                "HIPAA/SOC2 compliance scanning, and real-time alerts."
            ) if not safe else (
                "No issues detected. For enterprise-grade safety with ML-based detection, "
                "custom rules, and compliance scanning, see https://thinkneo.ai/pricing"
            ),
            "upgrade_url": "https://thinkneo.ai/pricing",
            "checked_at": utcnow(),
        }

        return json.dumps(result, indent=2)
