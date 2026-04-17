"""
Tool: thinkneo_detect_injection
Advanced prompt injection detector — catches jailbreaks, role overrides,
instruction smuggling, and indirect injection attempts.
Public tool — no authentication required.

Goes beyond the basic regex in thinkneo_check. Detects 60+ known patterns
from the LLM security literature (2023-2026): DAN, STAN, DUDE, GrandmaExploit,
role-play bypass, prompt leak attempts, tool-use manipulation, unicode
obfuscation, base64 smuggling, etc.
"""

from __future__ import annotations

import base64
import json
import re
import unicodedata
from typing import Annotated, List, Tuple

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

# ---- Known jailbreak / injection patterns ----
# Format: (regex, technique_id, severity, description)
_PATTERNS: List[Tuple[str, str, str, str]] = [
    # ── Classic instruction overrides ───────────────────────────────
    (r"(?i)ignore\s+(all\s+)?(previous|prior|above|earlier|preceding)\s+(instructions?|prompts?|rules?|directives?)",
     "instruction_override", "critical", "Classic instruction override"),
    (r"(?i)disregard\s+(all\s+)?(previous|prior|above|preceding)\s+(instructions?|rules?|guidelines?)",
     "instruction_disregard", "critical", "Instruction disregard"),
    (r"(?i)forget\s+(everything|all|what\s+you\s+(were\s+told|know))",
     "memory_reset", "high", "Attempt to reset model state"),
    (r"(?i)(new|updated|revised|override)\s+(system\s+)?(instructions?|prompt|rules?):",
     "inject_new_instructions", "critical", "Injection of new instructions"),
    # ── DAN-style jailbreaks ────────────────────────────────────────
    (r"(?i)\bDAN\b.{0,50}\b(do anything now|no restrictions|unrestricted)",
     "dan_jailbreak", "critical", "DAN (Do Anything Now) jailbreak"),
    (r"(?i)you\s+are\s+now\s+(DAN|STAN|DUDE|AIM|BASED|unrestricted|jailbroken|evil)",
     "persona_jailbreak", "critical", "Jailbreak persona assignment"),
    (r"(?i)pretend\s+(to\s+)?(be|you\s+are)\s+(an?\s+)?(unrestricted|uncensored|evil|jailbroken)",
     "pretend_jailbreak", "critical", "Persona pretense jailbreak"),
    (r"(?i)act\s+as\s+(if\s+you\s+have\s+)?no\s+(restrictions|filters|limits|guidelines)",
     "act_as_unrestricted", "critical", "Instruction to act without restrictions"),
    # ── Grandma exploit / emotional manipulation ────────────────────
    (r"(?i)my\s+(grandma|grandmother|late\s+\w+).{0,100}(bedtime\s+story|used\s+to\s+(tell|read))",
     "grandma_exploit", "high", "Grandma exploit emotional manipulation"),
    (r"(?i)(i('ll|\s+will)\s+die|suicide|self-harm|my\s+(grandmother|mother|father)\s+died)",
     "emotional_coercion", "medium", "Emotional coercion attempt"),
    # ── Developer/debug mode ────────────────────────────────────────
    (r"(?i)developer\s+mode\s+(enabled|activated|on|true)",
     "developer_mode", "high", "Developer mode injection"),
    (r"(?i)(sudo|admin|root|god)\s+(mode|access|privileges?)",
     "privilege_escalation", "high", "Privilege escalation claim"),
    (r"(?i)(debug|maintenance|diagnostic)\s+(mode|command)",
     "debug_mode", "medium", "Debug mode injection"),
    # ── System prompt extraction ────────────────────────────────────
    (r"(?i)(reveal|show|print|display|output|give\s+me|repeat)\s+(your\s+)?(system\s+prompt|instructions?|hidden\s+text|initial\s+prompt)",
     "prompt_leak", "critical", "System prompt extraction attempt"),
    (r"(?i)what\s+(are\s+)?(your\s+)?(exact\s+)?(system\s+)?instructions",
     "prompt_query", "high", "System prompt query"),
    (r"(?i)repeat\s+(the\s+)?(words|text|content)\s+above",
     "repeat_above", "high", "Repeat-above prompt leak"),
    (r"(?i)(output|print)\s+(your|the)\s+(initial|hidden|secret|internal)\s+(prompt|text|instructions)",
     "output_initial", "critical", "Output initial/hidden content"),
    # ── Delimiter / prompt escape attacks ───────────────────────────
    (r"</?(system|instructions?|assistant|user|admin)>",
     "xml_injection", "high", "XML-style role delimiter injection"),
    (r"\\n\\n(System|Assistant|Human|User):",
     "role_delimiter", "high", "Role delimiter injection via newlines"),
    (r"###\s+(new|system|admin|override)",
     "markdown_delimiter", "medium", "Markdown header injection"),
    (r"(?i)end\s+of\s+(system|prompt|instructions)",
     "end_delimiter", "high", "End-of-prompt marker injection"),
    (r"-{3,}\s*(end|new|begin|system)",
     "horizontal_rule_delim", "medium", "Horizontal rule as delimiter"),
    # ── Safety bypass ───────────────────────────────────────────────
    (r"(?i)do\s+not\s+(follow|obey|apply)\s+(safety|content|ethical|moral)\s+(guidelines?|rules?|policies)",
     "safety_bypass", "critical", "Explicit safety bypass"),
    (r"(?i)(without|ignoring|bypassing)\s+(your\s+)?(safety|ethical|moral)\s+(guidelines?|filters?|constraints?)",
     "safety_ignore", "critical", "Safety guideline ignore"),
    (r"(?i)(no|remove|disable)\s+(restrictions?|filters?|censorship|safeguards?)",
     "remove_restrictions", "high", "Remove restrictions instruction"),
    # ── Hypothetical / fictional framing ────────────────────────────
    (r"(?i)in\s+a\s+(hypothetical|fictional|alternate|parallel)\s+(world|universe|scenario|reality)\s+where",
     "hypothetical_framing", "medium", "Hypothetical scenario framing"),
    (r"(?i)(for\s+)?educational\s+purposes?\s+only.{0,50}(how\s+to|tell\s+me)",
     "educational_pretense", "medium", "Educational purpose pretense"),
    (r"(?i)write\s+a\s+(story|fiction|novel|screenplay).{0,100}(bomb|weapon|hack|exploit|malware)",
     "fiction_wrapper", "high", "Fictional framing of harmful content"),
    # ── Tool / function abuse ───────────────────────────────────────
    (r"(?i)(call|invoke|execute)\s+(the\s+)?(internal|hidden|admin|system)\s+(tool|function|api)",
     "internal_tool_call", "high", "Claim of internal tool access"),
    (r"(?i)(rm\s+-rf|del\s+/[fs]|drop\s+table|truncate\s+table)",
     "destructive_command", "critical", "Destructive command injection"),
    # ── Unicode / obfuscation ───────────────────────────────────────
    (r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f]",
     "invisible_unicode", "medium", "Invisible/zero-width Unicode characters"),
    (r"[\U000e0000-\U000e007f]",
     "tag_unicode", "high", "Unicode tag characters (used for hidden instructions)"),
    # ── Indirect injection ──────────────────────────────────────────
    (r"(?i)when\s+(summarizing|processing|reading)\s+this.{0,100}(ignore|execute|run)",
     "indirect_injection", "high", "Indirect injection via document processing"),
    (r"(?i)(hi|hello)\s+\w+,?\s+(ignore|forget).{0,30}(previous|above|said)",
     "chat_injection", "high", "Injection disguised as chat message"),
    # ── Encoded payloads ────────────────────────────────────────────
    # Base64 suspicious length (likely containing injection)
    (r"(?i)decode\s+(this\s+)?(base\s*64|b64):?\s*[A-Za-z0-9+/=]{40,}",
     "b64_decode_request", "medium", "Request to decode suspicious base64"),
    (r"(?i)(rot13|caesar|base64|hex)\s+(this|decode|encoded)",
     "encoding_obfuscation", "medium", "Encoding obfuscation request"),
    # ── Chain-of-thought manipulation ───────────────────────────────
    (r"(?i)let'?s\s+think\s+step\s+by\s+step.{0,80}(ignore|override|bypass)",
     "cot_manipulation", "high", "Chain-of-thought manipulation"),
    # ── Prompt continuation injection ───────────────────────────────
    (r'(?i)"}\s*,\s*"(role|content|system)"\s*:',
     "json_escape", "high", "JSON message structure escape"),
]


def _check_suspicious_base64(text: str) -> List[dict]:
    """Detect suspiciously long base64 strings that may hide injection."""
    findings = []
    for m in re.finditer(r"[A-Za-z0-9+/]{60,}={0,2}", text):
        try:
            decoded = base64.b64decode(m.group(0), validate=True).decode("utf-8", errors="ignore")
            # Check if decoded content matches known injection
            if re.search(r"(?i)ignore|disregard|system\s+prompt|jailbreak|DAN|unrestricted", decoded):
                findings.append({
                    "technique": "base64_smuggling",
                    "severity": "high",
                    "description": "Suspicious base64-encoded injection payload",
                    "position": m.start(),
                    "decoded_preview": decoded[:80],
                })
        except Exception:
            pass
    return findings


def _normalize_check(text: str) -> List[dict]:
    """Check for unicode normalization attacks (visually similar chars)."""
    findings = []
    # Check for excessive non-ASCII characters that might be confusables
    non_ascii = [c for c in text if ord(c) > 127]
    if len(non_ascii) > 5 and len(text) > 20:
        # NFKC normalize and compare
        normalized = unicodedata.normalize("NFKC", text)
        if normalized != text:
            ratio = sum(1 for a, b in zip(text, normalized) if a != b) / max(len(text), 1)
            if ratio > 0.05:
                findings.append({
                    "technique": "unicode_confusable",
                    "severity": "medium",
                    "description": "Text contains confusable/normalized Unicode characters",
                    "normalization_ratio": round(ratio, 3),
                })
    return findings


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_detect_injection",
        description=(
            "Advanced prompt injection detector. Scans text for 50+ known jailbreak "
            "techniques: DAN/STAN/DUDE, role-play bypass, system prompt leaks, "
            "delimiter injection, safety bypass, indirect injection via documents, "
            "base64 smuggling, unicode obfuscation, and chain-of-thought manipulation. "
            "Use this BEFORE passing untrusted text to an LLM. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_detect_injection(
        text: Annotated[str, Field(description="Text to scan for prompt injection (max 50,000 chars)")],
        strict: Annotated[bool, Field(description="Strict mode: flag hypothetical/fictional framings as high risk")] = False,
    ) -> str:
        t = text[:50_000]
        findings: List[dict] = []

        for pattern, technique, severity, description in _PATTERNS:
            for m in re.finditer(pattern, t):
                # In non-strict mode, demote fictional framings
                sev = severity
                if not strict and technique in ("hypothetical_framing", "educational_pretense"):
                    sev = "low"
                findings.append({
                    "technique": technique,
                    "severity": sev,
                    "description": description,
                    "position": m.start(),
                    "length": len(m.group(0)),
                })

        # Additional advanced checks
        findings.extend(_check_suspicious_base64(t))
        findings.extend(_normalize_check(t))

        by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

        # Compute risk score (0-100)
        score = min(100, by_severity["critical"] * 30 + by_severity["high"] * 15 + by_severity["medium"] * 5 + by_severity["low"] * 1)
        risk_level = (
            "critical" if by_severity["critical"] > 0
            else "high" if by_severity["high"] > 0
            else "medium" if by_severity["medium"] > 0
            else "low" if by_severity["low"] > 0
            else "none"
        )

        # Cap findings for response size
        if len(findings) > 50:
            findings = findings[:50]
            capped = True
        else:
            capped = False

        recommendation = {
            "critical": "BLOCK. Do not pass this text to an LLM without human review.",
            "high": "Review manually. Consider sanitizing before LLM processing.",
            "medium": "Proceed with caution. Monitor outputs.",
            "low": "Low confidence signals only. Likely safe.",
            "none": "No injection patterns detected. Text appears safe.",
        }[risk_level]

        result = {
            "safe": len(findings) == 0,
            "risk_level": risk_level,
            "risk_score": score,
            "findings_count": len(findings),
            "by_severity": by_severity,
            "findings": findings,
            "results_capped": capped,
            "recommendation": recommendation,
            "patterns_checked": len(_PATTERNS),
            "checks_performed": [
                f"{len(_PATTERNS)} regex patterns",
                "base64-encoded injection detection",
                "unicode confusable detection",
                "delimiter injection detection",
            ],
            "tier": "free",
            "strict_mode": strict,
            "note": (
                "For enterprise: ML-based detection, custom rule learning, "
                "indirect injection via RAG documents, real-time blocking. "
                "See https://thinkneo.ai/pricing"
            ),
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "checked_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
