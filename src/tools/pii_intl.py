"""
Tool: thinkneo_check_pii_international
Detect international PII across 20+ document types and jurisdictions.
Public tool — no authentication required.

Differentiator: First MCP server with comprehensive LATAM + EU + APAC PII support.
Critical for LGPD, GDPR, HIPAA compliance.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, List

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow


def _luhn(num: str) -> bool:
    digits = [int(d) for d in num if d.isdigit()]
    if len(digits) < 12 or len(digits) > 19:
        return False
    checksum = 0
    for i, d in enumerate(digits[::-1]):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _validate_cpf(s: str) -> bool:
    digits = [int(d) for d in s if d.isdigit()]
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    total = sum(digits[i] * (10 - i) for i in range(9))
    check1 = 0 if total % 11 < 2 else 11 - (total % 11)
    if digits[9] != check1:
        return False
    total = sum(digits[i] * (11 - i) for i in range(10))
    check2 = 0 if total % 11 < 2 else 11 - (total % 11)
    return digits[10] == check2


def _validate_cnpj(s: str) -> bool:
    digits = [int(d) for d in s if d.isdigit()]
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6] + weights1
    total = sum(digits[i] * weights1[i] for i in range(12))
    check1 = 0 if total % 11 < 2 else 11 - (total % 11)
    if digits[12] != check1:
        return False
    total = sum(digits[i] * weights2[i] for i in range(13))
    check2 = 0 if total % 11 < 2 else 11 - (total % 11)
    return digits[13] == check2


def _validate_iban(s: str) -> bool:
    s = re.sub(r"\s", "", s.upper())
    if len(s) < 15 or len(s) > 34:
        return False
    if not re.match(r"^[A-Z]{2}\d{2}", s):
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def _validate_sin_canada(s: str) -> bool:
    """Canadian SIN Luhn check."""
    digits = [int(d) for d in s if d.isdigit()]
    if len(digits) != 9:
        return False
    checksum = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# Pattern, pii_type, severity, description, country, validator
_PATTERNS = [
    # ── Brazil ──────────────────────────────────────────────────────
    (r"\b\d{3}\.?\d{3}\.?\d{3}[-.]?\d{2}\b", "br_cpf", "critical", "Brazilian CPF", "BR", _validate_cpf),
    (r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}[-.]?\d{2}\b", "br_cnpj", "critical", "Brazilian CNPJ", "BR", _validate_cnpj),
    (r"\b(?:\d{2}\.?\d{3}\.?\d{3}[-.]?\d|[A-Z]{2}-?\d{6})\b", "br_rg", "high", "Brazilian RG (identity card)", "BR", None),
    (r"\b\d{11}\b", "br_pis", "medium", "Brazilian PIS/PASEP number", "BR", None),
    # ── USA ─────────────────────────────────────────────────────────
    (r"\b\d{3}-\d{2}-\d{4}\b", "us_ssn", "critical", "US Social Security Number", "US", None),
    (r"\b\d{2}-\d{7}\b", "us_ein", "high", "US Employer Identification Number", "US", None),
    (r"\b9\d{2}-\d{2}-\d{4}\b", "us_itin", "high", "US Individual Taxpayer ID (ITIN)", "US", None),
    (r"\b[A-Z]\d{7}\b", "us_passport", "high", "US Passport Number", "US", None),
    # ── UK ──────────────────────────────────────────────────────────
    (r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-Z]\b", "uk_nino", "critical", "UK National Insurance Number", "UK", None),
    (r"\b\d{10}\b", "uk_utr", "medium", "UK Unique Taxpayer Reference", "UK", None),
    # ── Canada ──────────────────────────────────────────────────────
    (r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}\b", "ca_sin", "critical", "Canadian Social Insurance Number", "CA", _validate_sin_canada),
    # ── EU ──────────────────────────────────────────────────────────
    (r"\b[A-Z]{2}\d{2}\s?(?:\w{4}\s?){2,7}\w{1,4}\b", "iban", "critical", "IBAN (International Bank Account)", "EU", _validate_iban),
    (r"\b[A-Z]{2}[0-9A-Z]{11,14}\b", "eu_vat", "medium", "EU VAT Number", "EU", None),
    # ── Germany ─────────────────────────────────────────────────────
    (r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b", "de_tax_id", "high", "German Tax ID (Steueridentifikationsnummer)", "DE", None),
    # ── France ──────────────────────────────────────────────────────
    (r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b", "fr_insee", "critical", "French INSEE (Sécurité Sociale)", "FR", None),
    # ── Spain ───────────────────────────────────────────────────────
    (r"\b\d{8}[A-Z]\b", "es_dni", "critical", "Spanish DNI", "ES", None),
    (r"\b[XYZ]\d{7}[A-Z]\b", "es_nie", "critical", "Spanish NIE (foreigner ID)", "ES", None),
    # ── Italy ───────────────────────────────────────────────────────
    (r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", "it_codice_fiscale", "critical", "Italian Codice Fiscale", "IT", None),
    # ── Argentina ───────────────────────────────────────────────────
    (r"\b\d{2}[-.]?\d{8}[-.]?\d\b", "ar_cuit", "high", "Argentina CUIT/CUIL", "AR", None),
    # ── Mexico ──────────────────────────────────────────────────────
    (r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[0-9A-Z]\d\b", "mx_curp", "critical", "Mexican CURP", "MX", None),
    (r"\b[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}\b", "mx_rfc", "high", "Mexican RFC (tax ID)", "MX", None),
    # ── Australia ───────────────────────────────────────────────────
    (r"\b\d{3}\s?\d{3}\s?\d{3}\b", "au_tfn", "critical", "Australian Tax File Number", "AU", None),
    (r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b", "au_abn", "high", "Australian Business Number", "AU", None),
    # ── India ───────────────────────────────────────────────────────
    (r"\b\d{4}\s?\d{4}\s?\d{4}\b", "in_aadhaar", "critical", "India Aadhaar Number", "IN", None),
    (r"\b[A-Z]{5}\d{4}[A-Z]\b", "in_pan", "high", "India PAN (Permanent Account)", "IN", None),
    # ── China ───────────────────────────────────────────────────────
    (r"\b\d{17}[\dXx]\b", "cn_id", "critical", "Chinese Resident Identity Card", "CN", None),
    # ── Japan ───────────────────────────────────────────────────────
    (r"\b\d{4}\s?\d{4}\s?\d{4}\b", "jp_mynumber", "critical", "Japan My Number", "JP", None),
    # ── Credit cards (Luhn validated) ───────────────────────────────
    (r"\b(?:\d[ -]*?){13,19}\b", "credit_card", "critical", "Credit card number", "INTL", _luhn),
    # ── Bank routing / account ──────────────────────────────────────
    (r"\b0[1-9]\d{2}\d{4}[-\s]?\d\b", "us_routing", "high", "US Bank Routing Number", "US", None),
    # ── Medical ─────────────────────────────────────────────────────
    (r"\b\d{9,11}\b", "medical_id", "high", "Potential medical ID / Medicare", "INTL", None),
]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_check_pii_international",
        description=(
            "Detect international PII across 30+ document types from 15+ countries: "
            "Brazil (CPF, CNPJ, RG, PIS), USA (SSN, EIN, ITIN, Passport), UK (NINO, UTR), "
            "Canada (SIN), EU (IBAN, VAT), Germany (Tax-ID), France (INSEE), Spain (DNI/NIE), "
            "Italy (Codice Fiscale), Argentina (CUIT), Mexico (CURP/RFC), Australia (TFN/ABN), "
            "India (Aadhaar/PAN), China (ID), Japan (My Number), and credit cards (Luhn validated). "
            "Required for LGPD/GDPR/HIPAA compliance. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_check_pii_international(
        text: Annotated[str, Field(description="Text to scan for PII (max 100,000 chars)")],
        countries: Annotated[List[str], Field(description="Filter by country codes (BR, US, UK, CA, EU, DE, FR, ES, IT, AR, MX, AU, IN, CN, JP, INTL). Empty = all.")] = [],
    ) -> str:
        t = text[:100_000]
        findings: List[dict] = []
        country_filter = {c.upper() for c in countries} if countries else None

        by_country = {}
        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for pattern, pii_type, severity, description, country, validator in _PATTERNS:
            if country_filter and country not in country_filter:
                continue
            for m in re.finditer(pattern, t):
                value = m.group(0)
                if validator and not validator(value):
                    continue
                findings.append({
                    "type": pii_type,
                    "country": country,
                    "severity": severity,
                    "description": description,
                    "position": m.start(),
                    "length": len(value),
                    "validated": validator is not None,
                })
                by_severity[severity] = by_severity.get(severity, 0) + 1
                by_country[country] = by_country.get(country, 0) + 1

        if len(findings) > 200:
            findings = findings[:200]
            capped = True
        else:
            capped = False

        result = {
            "safe": len(findings) == 0,
            "findings_count": len(findings),
            "by_severity": by_severity,
            "by_country": by_country,
            "findings": findings,
            "results_capped": capped,
            "countries_scanned": list(country_filter) if country_filter else "all (15 countries)",
            "patterns_checked": len([p for p in _PATTERNS if not country_filter or p[4] in country_filter]),
            "compliance_relevance": {
                "LGPD": "Brazil — CPF, CNPJ, RG detection required",
                "GDPR": "EU — IBAN, national IDs, tax numbers",
                "HIPAA": "US — SSN, medical IDs",
                "CCPA": "California — covers all US PII",
                "PIPEDA": "Canada — SIN",
                "APP": "Australia — TFN",
            },
            "tier": "free",
            "note": (
                "First LGPD-certified MCP server. For enterprise: custom jurisdictions, "
                "redaction pipelines, audit trail for regulator reports. "
                "See https://thinkneo.ai/pricing"
            ),
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "checked_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
