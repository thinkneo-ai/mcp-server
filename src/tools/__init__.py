# Tool modules — each module registers its tool(s) via register(mcp) call.
import functools
import json
import logging

from .alerts import register as register_alerts
from .budget import register as register_budget
from .compliance import register as register_compliance
from .guardrails import register as register_guardrails
from .guardrails_free import register as register_guardrails_free
from .policy import register as register_policy
from .providers import register as register_providers
from .scheduling import register as register_scheduling
from .memory import register as register_memory
from .spend import register as register_spend
from .usage import register as register_usage
from .registry import register as register_registry
from .write_memory import register as register_write_memory
from .router_route import register as register_router_route
from .router_savings import register as register_router_savings
from .router_simulate import register as register_router_simulate
from .trust_score import register as register_trust_score
from .bridge import register as register_bridge
from .observability import register as register_observability
from .value_baseline import register as register_value_baseline
from .value_log_decision import register as register_value_log_decision
from .value_log_risk import register as register_value_log_risk
from .value_decision_cost import register as register_value_decision_cost
from .value_agent_roi import register as register_value_agent_roi
from .value_business_impact import register as register_value_business_impact
from .a2a_log import register as register_a2a_log
from .a2a_policy import register as register_a2a_policy
from .a2a_flow import register as register_a2a_flow
from .a2a_audit import register as register_a2a_audit
from .value_waste_detector import register as register_waste_detector
from .outcome_validation import register as register_outcome_validation
from .policy_engine import register as register_policy_engine
from .benchmarking import register as register_benchmarking
from .compliance_export import register as register_compliance_export
from .agent_sla import register as register_agent_sla

logger = logging.getLogger(__name__)


def register_all(mcp) -> None:
    """Register all ThinkNEO tools on the given FastMCP instance."""
    register_spend(mcp)
    register_memory(mcp)
    register_write_memory(mcp)
    register_guardrails(mcp)
    register_guardrails_free(mcp)
    register_policy(mcp)
    register_budget(mcp)
    register_alerts(mcp)
    register_compliance(mcp)
    register_providers(mcp)
    register_scheduling(mcp)
    register_usage(mcp)
    register_router_route(mcp)
    register_router_savings(mcp)
    register_router_simulate(mcp)
    register_trust_score(mcp)
    register_registry(mcp)

    # MCP <-> A2A Bridge tools
    register_bridge(mcp)
    # Agent Observability tools (2026-04-18)
    register_observability(mcp)

    # Business Value Attribution tools (2026-04-23)
    register_value_baseline(mcp)
    register_value_log_decision(mcp)
    register_value_log_risk(mcp)
    register_value_decision_cost(mcp)
    register_value_agent_roi(mcp)
    register_value_business_impact(mcp)

    # A2A Control Layer tools (2026-04-23)
    register_a2a_log(mcp)
    register_a2a_policy(mcp)
    register_a2a_flow(mcp)
    register_a2a_audit(mcp)

    # Optimization & Waste Detection (2026-04-23)
    register_waste_detector(mcp)

    # Outcome Validation Loop — "From Prompt to Proof" (2026-04-24)
    register_outcome_validation(mcp)

    # Policy Engine — Governance-as-Code (2026-04-24)
    register_policy_engine(mcp)

    # Outcome Benchmarking — Quality-Based Routing (2026-04-24)
    register_benchmarking(mcp)

    # Compliance Export — One-click regulatory reports (2026-04-24)
    register_compliance_export(mcp)

    # Agent SLA — Outcome Service Level Agreements (2026-04-24)
    register_agent_sla(mcp)

    # After all tools are registered, wrap each tool's function
    # to integrate free-tier checking and usage footer injection.
    _wrap_tools_with_free_tier(mcp)


def _wrap_tools_with_free_tier(mcp) -> None:
    """
    Wrap all registered tool functions to add:
    1. Free-tier limit check before execution
    2. Usage footer (_usage) appended to JSON responses

    All original tool functions are synchronous, so wrappers are sync too.
    """
    from ..free_tier import check_free_tier, get_usage_footer

    # Access the internal tool registry.
    # FastMCP stores tools in _tool_manager._tools (dict[name, Tool]).
    # NOTE: This accesses private API — pin mcp[cli] version in requirements.txt.
    try:
        tool_manager = mcp._tool_manager
        tools = tool_manager._tools
    except AttributeError:
        logger.warning(
            "Could not access FastMCP tool registry for free-tier wrapping. "
            "This likely means the mcp library version changed its internal API. "
            "Pin mcp version in requirements.txt to avoid this."
        )
        return

    for tool_name, tool_obj in tools.items():
        original_fn = tool_obj.fn

        # Create a wrapper that preserves the original function's full signature
        # using functools.wraps so inspect.signature() follows __wrapped__.
        def make_wrapper(orig_fn, tname):
            @functools.wraps(orig_fn)
            def wrapped(*args, **kwargs):
                # 1. Check free tier limits
                block_msg = check_free_tier(tname)
                if block_msg:
                    return block_msg

                # 2. Call original function (with OTEL span if enabled)
                from ..otel import is_otel_enabled, get_tracer, tool_calls_total, tool_duration_seconds
                import time as _time

                if is_otel_enabled() and get_tracer():
                    tracer = get_tracer()
                    with tracer.start_as_current_span(f"tool.{tname}") as span:
                        span.set_attribute("thinkneo.tool_name", tname)
                        span.set_attribute("thinkneo.tool_type", "mcp")
                        start = _time.perf_counter()
                        try:
                            result = orig_fn(*args, **kwargs)
                            span.set_attribute("thinkneo.tool_status", "ok")
                            if tool_calls_total:
                                tool_calls_total.add(1, {"tool": tname, "status": "ok"})
                            return result
                        except Exception as exc:
                            span.set_attribute("thinkneo.tool_status", "error")
                            span.record_exception(exc)
                            if tool_calls_total:
                                tool_calls_total.add(1, {"tool": tname, "status": "error"})
                            raise
                        finally:
                            duration = _time.perf_counter() - start
                            if tool_duration_seconds:
                                tool_duration_seconds.record(duration, {"tool": tname})
                else:
                    result = orig_fn(*args, **kwargs)

                # 3. Append usage footer to JSON responses
                try:
                    footer = get_usage_footer(tname)
                    if footer and isinstance(result, str):
                        parsed = json.loads(result)
                        if isinstance(parsed, dict):
                            parsed["_usage"] = footer
                            return json.dumps(parsed, indent=2, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    pass

                return result

            return wrapped

        tool_obj.fn = make_wrapper(original_fn, tool_name)

    logger.info("Wrapped %d tools with free-tier middleware", len(tools))
