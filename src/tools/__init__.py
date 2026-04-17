# Tool modules — each module registers its tool(s) via register(mcp) call.
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
from .write_memory import register as register_write_memory

# New tools (2026-04-16)
from .secrets import register as register_secrets
from .injection import register as register_injection
from .compare_models import register as register_compare_models
from .optimize_prompt import register as register_optimize_prompt
from .tokens import register as register_tokens
from .pii_intl import register as register_pii_intl
from .cache import register as register_cache
from .rotate_key import register as register_rotate_key

logger = logging.getLogger(__name__)


def register_all(mcp) -> None:
    """Register all ThinkNEO tools on the given FastMCP instance."""
    # Existing tools
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

    # New free tools
    register_secrets(mcp)
    register_injection(mcp)
    register_compare_models(mcp)
    register_optimize_prompt(mcp)
    register_tokens(mcp)
    register_pii_intl(mcp)

    # New paid/caching tools
    register_cache(mcp)
    register_rotate_key(mcp)

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

    # Access the internal tool registry
    # FastMCP stores tools in _tool_manager._tools (dict[name, Tool])
    try:
        tool_manager = mcp._tool_manager
        tools = tool_manager._tools
    except AttributeError:
        logger.warning("Could not access FastMCP tool registry for free-tier wrapping")
        return

    for tool_name, tool_obj in tools.items():
        original_fn = tool_obj.fn

        # Create a sync wrapper that preserves the original function's signature
        def make_wrapper(orig_fn, tname):
            def wrapped(*args, **kwargs):
                # 1. Check free tier limits
                block_msg = check_free_tier(tname)
                if block_msg:
                    return block_msg

                # 2. Call original function (sync)
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

            # Preserve function metadata for FastMCP
            wrapped.__name__ = orig_fn.__name__
            wrapped.__doc__ = orig_fn.__doc__
            wrapped.__module__ = getattr(orig_fn, '__module__', __name__)
            # Copy annotations for parameter detection
            if hasattr(orig_fn, '__annotations__'):
                wrapped.__annotations__ = orig_fn.__annotations__
            if hasattr(orig_fn, '__wrapped__'):
                wrapped.__wrapped__ = orig_fn.__wrapped__
            return wrapped

        tool_obj.fn = make_wrapper(original_fn, tool_name)

    logger.info("Wrapped %d tools with free-tier middleware", len(tools))
