"""
Tool: thinkneo_optimize_prompt
Heuristic prompt optimizer — identifies redundancy, ambiguity, missing structure,
and suggests token-reducing rewrites.
Public tool — no authentication required.

Saves real money by helping devs write tighter prompts. ThinkNEO earns SEO
visits every time a dev wonders "how do I optimize my LLM prompt".
"""

from __future__ import annotations

import json
import re
from typing import Annotated, List

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

_FILLER_WORDS = {
    "basically", "actually", "really", "very", "quite", "rather", "somewhat",
    "kind of", "sort of", "just", "simply", "essentially", "literally",
    "obviously", "clearly", "needless to say", "to be honest",
    "as a matter of fact", "at the end of the day", "in order to",
    "in the event that", "due to the fact that", "at this point in time",
    "for the purpose of", "with regard to", "with respect to",
}

_VERBOSE_PHRASES = {
    "in order to": "to",
    "due to the fact that": "because",
    "at this point in time": "now",
    "for the purpose of": "to",
    "with regard to": "about",
    "with respect to": "about",
    "a large number of": "many",
    "a significant amount of": "much",
    "in the event that": "if",
    "at the present time": "now",
    "in spite of the fact that": "although",
    "it is important to note that": "note that",
    "it should be mentioned that": "",
    "please be advised that": "",
    "as a matter of fact": "",
}

_HEDGING = [
    r"\b(I think|I believe|I feel|I guess|I suppose|perhaps|maybe|possibly)\b",
    r"\b(might|could potentially|may possibly|tend to|seem to)\b",
]

# Rough token estimation: ~4 chars per token (English), 0.75 tokens per word
def _estimate_tokens(text: str) -> int:
    # Simple heuristic averaging chars/4 and words*0.75
    by_chars = len(text) / 4
    by_words = len(text.split()) * 0.75
    return int((by_chars + by_words) / 2)


def _analyze_structure(text: str) -> List[str]:
    suggestions = []
    if len(text) < 20:
        suggestions.append("Prompt is very short — consider adding context, constraints, and expected output format.")
    if not re.search(r"[.!?]", text):
        suggestions.append("No terminal punctuation found. Use clear sentences.")
    if not re.search(r"(?i)(output|return|respond|answer|provide|generate)", text):
        suggestions.append("No explicit output instruction. Tell the model what to produce (e.g., 'Return JSON with fields x, y').")
    if not re.search(r"(?i)(format|JSON|XML|YAML|markdown|bullet|numbered)", text):
        suggestions.append("No output format specified. Be explicit: 'Output as JSON', 'Use markdown', etc.")
    if len(text.split()) > 500 and "example" not in text.lower():
        suggestions.append("Long prompt (>500 words) without examples. Few-shot examples often reduce token usage AND improve quality.")
    if re.search(r"(?i)you (are|should|must)", text) and not re.search(r"(?i)role|persona", text):
        suggestions.append("Role instructions present. Consider opening with 'You are a [role]. Your task is to...' for clarity.")
    if "please" in text.lower() and text.lower().count("please") > 2:
        suggestions.append("Multiple 'please' found — polite filler. Models don't need it; it wastes tokens.")
    return suggestions


def _find_redundancy(text: str) -> List[dict]:
    findings = []
    lower = text.lower()

    # Filler words
    filler_found = []
    for f in _FILLER_WORDS:
        count = len(re.findall(rf"\b{re.escape(f)}\b", lower))
        if count > 0:
            filler_found.append({"word": f, "count": count})
    if filler_found:
        findings.append({
            "issue": "filler_words",
            "description": f"Found {sum(f['count'] for f in filler_found)} filler words that add no information.",
            "items": filler_found[:10],
        })

    # Verbose phrases with replacements
    replaceable = []
    for verbose, concise in _VERBOSE_PHRASES.items():
        if re.search(rf"\b{re.escape(verbose)}\b", lower):
            replaceable.append({"replace": verbose, "with": concise or "(remove)"})
    if replaceable:
        findings.append({
            "issue": "verbose_phrases",
            "description": f"Found {len(replaceable)} verbose phrases that can be shortened.",
            "replacements": replaceable[:10],
        })

    # Hedging language
    hedging_matches = []
    for pattern in _HEDGING:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            hedging_matches.append(m.group(0))
    if hedging_matches:
        findings.append({
            "issue": "hedging",
            "description": "Hedging words reduce instruction clarity. Remove when directing the model.",
            "matches": list(set(hedging_matches))[:10],
        })

    # Repeated phrases (3+ word n-grams that appear 3+ times)
    words = re.findall(r"\w+", text.lower())
    if len(words) > 20:
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
        from collections import Counter
        trigram_counts = Counter(trigrams).most_common(5)
        repeated = [{"phrase": p, "count": c} for p, c in trigram_counts if c >= 3]
        if repeated:
            findings.append({
                "issue": "repeated_phrases",
                "description": "Repeated phrases suggest redundancy.",
                "top_repeated": repeated,
            })

    # Excessive politeness
    if text.lower().count("please") + text.lower().count("thank you") + text.lower().count("thanks") > 3:
        findings.append({
            "issue": "excessive_politeness",
            "description": "Pleasantries waste tokens. Models respond to clear imperatives.",
        })

    return findings


def _rewrite_concise(text: str) -> str:
    """Aggressively shorten the prompt by applying known simplifications."""
    result = text
    for verbose, concise in _VERBOSE_PHRASES.items():
        pattern = re.compile(rf"\b{re.escape(verbose)}\b", re.IGNORECASE)
        result = pattern.sub(concise, result)
    # Remove hedging
    for pattern in _HEDGING:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    # Remove excessive politeness
    result = re.sub(r"(?i)\bplease\s+", "", result)
    result = re.sub(r"(?i)\s*,?\s*thank\s+you\b\s*\.?", "", result)
    result = re.sub(r"(?i)\s*,?\s*thanks\b\s*\.?", "", result)
    return result


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_optimize_prompt",
        description=(
            "Optimize an LLM prompt for clarity, conciseness, and token efficiency. "
            "Detects: filler words, verbose phrases, hedging language, repeated content, "
            "missing structure (output format, role, constraints), and excessive politeness. "
            "Returns suggestions + an automatically rewritten concise version with "
            "estimated token savings. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_optimize_prompt(
        prompt: Annotated[str, Field(description="The prompt text to optimize (max 20,000 chars)")],
    ) -> str:
        """Optimize an LLM prompt for clarity, conciseness, and token efficiency. Detects: filler words, verbose phrases, hedging language, repeated content, missing structure (output format, role, constraints), and excessive politeness. Returns suggestions + an automatically rewritten concise version with estimated token savings."""
        text = prompt[:20_000]
        original_tokens = _estimate_tokens(text)

        structure = _analyze_structure(text)
        redundancy = _find_redundancy(text)

        rewritten = _rewrite_concise(text)
        optimized_tokens = _estimate_tokens(rewritten)
        savings = max(0, original_tokens - optimized_tokens)
        savings_pct = round(100 * savings / max(1, original_tokens), 1)

        # Cost savings at GPT-5 prices (worst case)
        cost_per_m = 10.0  # GPT-5 input
        saved_cost_per_1k_calls = round((savings / 1_000_000) * cost_per_m * 1_000, 4)

        result = {
            "original_length_chars": len(text),
            "original_estimated_tokens": original_tokens,
            "optimized_estimated_tokens": optimized_tokens,
            "tokens_saved": savings,
            "savings_percent": savings_pct,
            "estimated_savings_per_1k_calls_usd": saved_cost_per_1k_calls,
            "structural_suggestions": structure,
            "redundancy_issues": redundancy,
            "optimized_prompt": rewritten if savings > 0 else text,
            "optimization_applied": savings > 0,
            "tips": [
                "Use imperatives ('Write...', 'Return...') not requests ('Could you please...')",
                "Specify output format explicitly (JSON schema, markdown, bullets)",
                "Put instructions BEFORE context for long documents",
                "Use delimiters (###, XML tags) to separate sections",
                "2-3 few-shot examples often beat long instructions",
                "Remove hedging — 'I think', 'maybe', 'perhaps' reduce clarity",
                "Specify constraints explicitly: length, tone, audience, style",
            ],
            "tier": "free",
            "note": (
                "For enterprise: A/B prompt testing, production prompt library, "
                "automatic optimization against your own eval suite. "
                "See https://thinkneo.ai/pricing"
            ),
            "docs_url": "https://mcp.thinkneo.ai/mcp/docs",
            "analyzed_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
