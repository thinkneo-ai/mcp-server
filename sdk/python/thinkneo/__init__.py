"""
ThinkNEO SDK — Enterprise AI Control Plane.

    from thinkneo import ThinkNEO

    tn = ThinkNEO(api_key="tnk_...")
    result = tn.check("Is this prompt safe?")
    print(result.safe)
"""

__version__ = "0.1.0"

from .client import AsyncThinkNEO, ThinkNEO
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    RateLimitError,
    ThinkNEOError,
    ToolError,
    ValidationError,
)
from .models import (
    AlertList,
    BudgetStatus,
    CacheResult,
    ComplianceStatus,
    DemoBooking,
    GenericResponse,
    GuardrailEvaluation,
    InjectionDetection,
    KeyRotation,
    MemoryRead,
    MemoryWrite,
    ModelComparison,
    PIICheck,
    PolicyCheck,
    PromptOptimization,
    ProviderStatus,
    SafetyCheck,
    SecretsScan,
    SpendReport,
    TokenEstimate,
    ToolResponse,
    UsageStats,
)

__all__ = [
    # Clients
    "ThinkNEO",
    "AsyncThinkNEO",
    # Exceptions
    "ThinkNEOError",
    "AuthenticationError",
    "RateLimitError",
    "ToolError",
    "ConnectionError",
    "ValidationError",
    # Models
    "ToolResponse",
    "SafetyCheck",
    "ProviderStatus",
    "UsageStats",
    "MemoryRead",
    "MemoryWrite",
    "DemoBooking",
    "SpendReport",
    "GuardrailEvaluation",
    "PolicyCheck",
    "BudgetStatus",
    "AlertList",
    "ComplianceStatus",
    "SecretsScan",
    "InjectionDetection",
    "ModelComparison",
    "PromptOptimization",
    "TokenEstimate",
    "PIICheck",
    "CacheResult",
    "KeyRotation",
    "GenericResponse",
]
