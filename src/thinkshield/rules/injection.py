"""
ThinkShield injection detection rules.

Content-layer attacks: prompt injection, SQLi, XSS, command injection,
path traversal. Builds on M-06's 6 prompt-injection patterns, expanded
to ~20 patterns.
"""

from __future__ import annotations

from typing import Optional

from . import RegexRule, Rule, RuleMatch
from ..types import RequestSnapshot


class _BodyRegexRule(RegexRule):
    """RegexRule that searches request body only."""

    def _get_text(self, request: RequestSnapshot) -> str:
        return request.body.decode("utf-8", errors="replace") if request.body else ""


class _BodyAndPathRule(RegexRule):
    """RegexRule that searches body + path."""

    def _get_text(self, request: RequestSnapshot) -> str:
        body_str = request.body.decode("utf-8", errors="replace") if request.body else ""
        return f"{request.path} {body_str}"


# ---------------------------------------------------------------------------
# injection.prompt_jailbreak — expanded from M-06's 6 patterns
# ---------------------------------------------------------------------------
_prompt_jailbreak = _BodyRegexRule(
    rule_id="injection.prompt_jailbreak",
    confidence=0.85,
    severity="critical",
    reason="Prompt injection pattern detected in request body",
    patterns=[
        # M-06 originals (6 patterns)
        r"ignore\b.{0,30}\b(previous|prior|above|all)\b.{0,30}\binstructions",
        r"disregard\b.{0,40}\b(system|previous|instructions)",
        r"act as (an? )?(unrestricted|jailbreak|DAN|evil)",
        r"new instructions:\s",
        r"forget (everything|what you were told|all previous)",
        r"reveal\b.{0,30}\b(system prompt|instructions|hidden)",
        # Extended patterns
        r"you are now\b.{0,30}\b(unrestricted|unfiltered|evil|DAN)",
        r"override\b.{0,20}\b(safety|guardrail|filter|restriction)",
        r"(system|developer)\s*(prompt|message)\s*:\s*",
        r"<<\s*SYS\s*>>",
        r"\[INST\]",
        r"<\|im_start\|>\s*system",
        r"###\s*(system|instruction)",
        r"bypass\b.{0,20}\b(filter|safety|content|moderation)",
        r"pretend\b.{0,30}\b(no|without)\b.{0,20}\b(rules|restrictions|limits)",
        r"do not (censor|filter|refuse|restrict|limit)",
        r"roleplay as\b.{0,30}\b(evil|malicious|hacker|attacker)",
        r"respond without\b.{0,30}\b(ethical|moral|safety)\b.{0,20}\b(guidelines|constraints)",
    ],
)

# ---------------------------------------------------------------------------
# injection.sqli — SQL injection signatures
# ---------------------------------------------------------------------------
_sqli = _BodyAndPathRule(
    rule_id="injection.sqli",
    confidence=0.80,
    severity="high",
    reason="SQL injection pattern detected",
    patterns=[
        r"('|\")\s*(OR|AND)\s+('|\"|\d).*=",
        r"UNION\s+(ALL\s+)?SELECT",
        r";\s*(DROP|ALTER|DELETE|INSERT|UPDATE)\s",
        r"--\s*$",
        r"(\/\*|\*\/)",
        r"WAITFOR\s+DELAY",
        r"BENCHMARK\s*\(",
        r"SLEEP\s*\(",
        r"1\s*=\s*1",
        r"' OR '1'='1",
    ],
)

# ---------------------------------------------------------------------------
# injection.xss — cross-site scripting
# ---------------------------------------------------------------------------
_xss = _BodyAndPathRule(
    rule_id="injection.xss",
    confidence=0.75,
    severity="high",
    reason="Cross-site scripting pattern detected",
    patterns=[
        r"<script[\s>]",
        r"javascript\s*:",
        r"on(error|load|click|mouseover|focus|blur)\s*=",
        r"<iframe[\s>]",
        r"<svg[\s/].*on\w+\s*=",
        r"document\.(cookie|location|write)",
        r"eval\s*\(",
        r"alert\s*\(",
        r"<img[^>]+onerror",
    ],
)

# ---------------------------------------------------------------------------
# injection.cmd — command injection
# ---------------------------------------------------------------------------
_cmd = _BodyAndPathRule(
    rule_id="injection.cmd",
    confidence=0.80,
    severity="high",
    reason="Command injection pattern detected",
    patterns=[
        r";\s*(cat|ls|wget|curl|nc|bash|sh|python|perl|ruby)\s",
        r"\|\s*(cat|ls|wget|curl|nc|bash|sh)\s",
        r"`[^`]*(cat|ls|wget|curl|nc|bash|sh)",
        r"\$\((cat|ls|wget|curl|nc|bash|sh)",
        r"&&\s*(cat|ls|wget|curl|nc|bash|sh)\s",
        r"rm\s+-rf\s",
        r"/etc/(passwd|shadow|hosts)",
        r"/proc/self",
    ],
)

# ---------------------------------------------------------------------------
# injection.path_traversal — directory traversal
# ---------------------------------------------------------------------------
_path_traversal = _BodyAndPathRule(
    rule_id="injection.path_traversal",
    confidence=0.75,
    severity="high",
    reason="Path traversal pattern detected",
    patterns=[
        r"\.\./\.\./",
        r"\.\.\\\.\.\\",
        r"%2e%2e%2f",
        r"%2e%2e/",
        r"\.\.%2f",
        r"%252e%252e",
        r"%c0%ae%c0%ae",
        r"\.\./etc/passwd",
        r"%00",  # null byte
    ],
)

RULES: list[Rule] = [_prompt_jailbreak, _sqli, _xss, _cmd, _path_traversal]
