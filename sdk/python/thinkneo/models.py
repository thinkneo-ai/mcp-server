"""
ThinkNEO SDK — Response models.

All tool responses are parsed into typed dataclasses for easy access.
The raw JSON dict is always available via the `.raw` attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass
class ToolResponse:
    """Base response returned by every tool call."""
    raw: dict = field(repr=False)

    @property
    def usage(self) -> dict | None:
        """Free-tier usage footer, if present."""
        return self.raw.get("_usage")


# ---------------------------------------------------------------------------
# Free-tier / public tools
# ---------------------------------------------------------------------------

@dataclass
class SafetyCheck(ToolResponse):
    """Response from thinkneo_check."""
    safe: bool = True
    warnings: list[dict] = field(default_factory=list)
    warnings_count: int = 0
    text_length: int = 0
    checks_performed: list[str] = field(default_factory=list)
    tier: str = "free"
    checked_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> SafetyCheck:
        return cls(
            raw=d,
            safe=d.get("safe", True),
            warnings=d.get("warnings", []),
            warnings_count=d.get("warnings_count", 0),
            text_length=d.get("text_length", 0),
            checks_performed=d.get("checks_performed", []),
            tier=d.get("tier", "free"),
            checked_at=d.get("checked_at", ""),
        )


@dataclass
class ProviderStatus(ToolResponse):
    """Response from thinkneo_provider_status."""
    providers: list[dict] = field(default_factory=list)
    total_providers: int = 0
    fetched_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> ProviderStatus:
        return cls(
            raw=d,
            providers=d.get("providers", []),
            total_providers=d.get("total_providers", 0),
            fetched_at=d.get("fetched_at", ""),
        )


@dataclass
class UsageStats(ToolResponse):
    """Response from thinkneo_usage."""
    authenticated: bool = False
    tier: str = "anonymous"
    fetched_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> UsageStats:
        return cls(
            raw=d,
            authenticated=d.get("authenticated", False),
            tier=d.get("tier", "anonymous"),
            fetched_at=d.get("fetched_at", ""),
        )


@dataclass
class MemoryRead(ToolResponse):
    """Response from thinkneo_read_memory."""
    filename: str = ""
    content: str = ""
    size_bytes: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> MemoryRead:
        return cls(
            raw=d,
            filename=d.get("filename", ""),
            content=d.get("content", ""),
            size_bytes=d.get("size_bytes", 0),
        )


@dataclass
class MemoryWrite(ToolResponse):
    """Response from thinkneo_write_memory."""
    status: str = ""
    filename: str = ""
    size_bytes: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> MemoryWrite:
        return cls(
            raw=d,
            status=d.get("status", ""),
            filename=d.get("filename", ""),
            size_bytes=d.get("size_bytes", 0),
        )


@dataclass
class DemoBooking(ToolResponse):
    """Response from thinkneo_schedule_demo."""
    success: bool = False
    next_steps: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> DemoBooking:
        return cls(
            raw=d,
            success=d.get("success", False),
            next_steps=d.get("next_steps", ""),
        )


# ---------------------------------------------------------------------------
# Authenticated tools
# ---------------------------------------------------------------------------

@dataclass
class SpendReport(ToolResponse):
    """Response from thinkneo_check_spend."""
    workspace: str = ""
    period: str = ""
    total_cost_usd: float = 0.0
    breakdown: dict = field(default_factory=dict)
    request_count: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> SpendReport:
        return cls(
            raw=d,
            workspace=d.get("workspace", ""),
            period=d.get("period", ""),
            total_cost_usd=d.get("total_cost_usd", 0.0),
            breakdown=d.get("breakdown", {}),
            request_count=d.get("request_count", 0),
        )


@dataclass
class GuardrailEvaluation(ToolResponse):
    """Response from thinkneo_evaluate_guardrail."""
    workspace: str = ""
    guardrail_mode: str = "monitor"
    status: str = ""
    risk_level: str = "none"
    violations: list[dict] = field(default_factory=list)
    action: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> GuardrailEvaluation:
        return cls(
            raw=d,
            workspace=d.get("workspace", ""),
            guardrail_mode=d.get("guardrail_mode", "monitor"),
            status=d.get("status", ""),
            risk_level=d.get("risk_level", "none"),
            violations=d.get("violations", []),
            action=d.get("action", ""),
        )


@dataclass
class PolicyCheck(ToolResponse):
    """Response from thinkneo_check_policy."""
    workspace: str = ""
    overall_allowed: bool = True
    checks: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> PolicyCheck:
        return cls(
            raw=d,
            workspace=d.get("workspace", ""),
            overall_allowed=d.get("overall_allowed", True),
            checks=d.get("checks", []),
        )


@dataclass
class BudgetStatus(ToolResponse):
    """Response from thinkneo_get_budget_status."""
    workspace: str = ""
    budget: dict = field(default_factory=dict)
    alerts: dict = field(default_factory=dict)
    projection: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> BudgetStatus:
        return cls(
            raw=d,
            workspace=d.get("workspace", ""),
            budget=d.get("budget", {}),
            alerts=d.get("alerts", {}),
            projection=d.get("projection", {}),
        )


@dataclass
class AlertList(ToolResponse):
    """Response from thinkneo_list_alerts."""
    workspace: str = ""
    alerts: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> AlertList:
        return cls(
            raw=d,
            workspace=d.get("workspace", ""),
            alerts=d.get("alerts", []),
            summary=d.get("summary", {}),
        )


@dataclass
class ComplianceStatus(ToolResponse):
    """Response from thinkneo_get_compliance_status."""
    workspace: str = ""
    framework: str = "general"
    governance_score: int = 0
    status: str = ""
    controls: dict = field(default_factory=dict)
    pending_actions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> ComplianceStatus:
        return cls(
            raw=d,
            workspace=d.get("workspace", ""),
            framework=d.get("framework", "general"),
            governance_score=d.get("governance_score", 0),
            status=d.get("status", ""),
            controls=d.get("controls", {}),
            pending_actions=d.get("pending_actions", []),
        )


# ---------------------------------------------------------------------------
# Extended tools (scan_secrets, detect_injection, compare_models, etc.)
# ---------------------------------------------------------------------------

@dataclass
class SecretsScan(ToolResponse):
    """Response from thinkneo_scan_secrets."""
    secrets_found: int = 0
    findings: list[dict] = field(default_factory=list)
    safe: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> SecretsScan:
        return cls(
            raw=d,
            secrets_found=d.get("secrets_found", 0),
            findings=d.get("findings", []),
            safe=d.get("safe", True),
        )


@dataclass
class InjectionDetection(ToolResponse):
    """Response from thinkneo_detect_injection."""
    is_injection: bool = False
    confidence: float = 0.0
    patterns_matched: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> InjectionDetection:
        return cls(
            raw=d,
            is_injection=d.get("is_injection", False),
            confidence=d.get("confidence", 0.0),
            patterns_matched=d.get("patterns_matched", []),
        )


@dataclass
class ModelComparison(ToolResponse):
    """Response from thinkneo_compare_models."""
    models: list[dict] = field(default_factory=list)
    recommendation: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> ModelComparison:
        return cls(
            raw=d,
            models=d.get("models", []),
            recommendation=d.get("recommendation", ""),
        )


@dataclass
class PromptOptimization(ToolResponse):
    """Response from thinkneo_optimize_prompt."""
    original_tokens: int = 0
    optimized_tokens: int = 0
    optimized_prompt: str = ""
    savings_pct: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> PromptOptimization:
        return cls(
            raw=d,
            original_tokens=d.get("original_tokens", 0),
            optimized_tokens=d.get("optimized_tokens", 0),
            optimized_prompt=d.get("optimized_prompt", ""),
            savings_pct=d.get("savings_pct", 0.0),
        )


@dataclass
class TokenEstimate(ToolResponse):
    """Response from thinkneo_estimate_tokens."""
    token_count: int = 0
    model: str = ""
    estimated_cost_usd: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> TokenEstimate:
        return cls(
            raw=d,
            token_count=d.get("token_count", 0),
            model=d.get("model", ""),
            estimated_cost_usd=d.get("estimated_cost_usd", 0.0),
        )


@dataclass
class PIICheck(ToolResponse):
    """Response from thinkneo_check_pii_international."""
    pii_found: bool = False
    findings: list[dict] = field(default_factory=list)
    jurisdictions_checked: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> PIICheck:
        return cls(
            raw=d,
            pii_found=d.get("pii_found", False),
            findings=d.get("findings", []),
            jurisdictions_checked=d.get("jurisdictions_checked", []),
        )


@dataclass
class CacheResult(ToolResponse):
    """Response from thinkneo_cache_lookup, thinkneo_cache_store, thinkneo_cache_stats."""
    hit: bool = False
    cached_response: Any = None
    stats: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> CacheResult:
        return cls(
            raw=d,
            hit=d.get("hit", False),
            cached_response=d.get("cached_response"),
            stats=d.get("stats", {}),
        )


@dataclass
class KeyRotation(ToolResponse):
    """Response from thinkneo_rotate_key."""
    success: bool = False
    new_key_prefix: str = ""
    expires_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> KeyRotation:
        return cls(
            raw=d,
            success=d.get("success", False),
            new_key_prefix=d.get("new_key_prefix", ""),
            expires_at=d.get("expires_at", ""),
        )


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

@dataclass
class GenericResponse(ToolResponse):
    """Fallback for any tool response not covered by a specific model."""

    @classmethod
    def from_dict(cls, d: dict) -> GenericResponse:
        return cls(raw=d)
