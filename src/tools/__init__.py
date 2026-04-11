# Tool modules — each module registers its tool(s) via register(mcp) call.
from .alerts import register as register_alerts
from .budget import register as register_budget
from .compliance import register as register_compliance
from .guardrails import register as register_guardrails
from .policy import register as register_policy
from .providers import register as register_providers
from .scheduling import register as register_scheduling
from .memory import register as register_memory
from .spend import register as register_spend


def register_all(mcp) -> None:
    """Register all ThinkNEO tools on the given FastMCP instance."""
    register_spend(mcp)
    register_memory(mcp)
    register_guardrails(mcp)
    register_policy(mcp)
    register_budget(mcp)
    register_alerts(mcp)
    register_compliance(mcp)
    register_providers(mcp)
    register_scheduling(mcp)
