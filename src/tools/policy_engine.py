"""
Tools: Policy Engine — Governance-as-Code for AI Agents

4 MCP tools:
  - thinkneo_policy_create: Create/update a declarative policy
  - thinkneo_policy_list: List all active policies
  - thinkneo_policy_evaluate: Evaluate a request context against all policies
  - thinkneo_policy_violations: View violation history
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import require_auth, get_bearer_token
from ..policy_engine import create_policy, list_policies, evaluate_policies, get_violations
from .._common_obs import utcnow_obs


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="thinkneo_policy_create",
        description=(
            "Create or update a declarative AI governance policy. Policies define rules "
            "that AI agents must follow — conditions are evaluated against request context, "
            "and effects (block, warn, require_approval, log) are enforced automatically. "
            "Supports versioning — updating a policy creates a new version and disables the old one. "
            "Part of the Policy Engine — Governance-as-Code. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_policy_create(
        name: Annotated[str, Field(description="Policy name (e.g., 'approval_over_10k', 'pii_blocked_models')")],
        conditions: Annotated[list, Field(
            description=(
                "List of conditions. Each condition: {field, operator, value}. "
                "Fields: 'model', 'provider', 'cost', 'task_type', 'agent_name', 'data_classification', 'action'. "
                "Operators: '==', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'contains', 'matches'. "
                "Example: [{\"field\": \"cost\", \"operator\": \">\", \"value\": 10000}]"
            )
        )],
        effect: Annotated[str, Field(
            description="Effect when all conditions match: 'block', 'warn', 'require_approval', or 'log'"
        )],
        description: Annotated[Optional[str], Field(
            description="Human-readable description of what this policy does"
        )] = None,
        scope: Annotated[Optional[dict], Field(
            description=(
                "Scope filter: {agents: ['agent-1', 'finance-*'], actions: ['approve_payment']}. "
                "Use ['*'] for all. Default: all agents and actions."
            )
        )] = None,
    ) -> str:
        token = require_auth()

        conds = conditions
        if isinstance(conds, str):
            conds = json.loads(conds)

        sc = scope
        if isinstance(sc, str):
            sc = json.loads(sc)

        result = create_policy(
            api_key=token,
            name=name,
            conditions=conds,
            effect=effect,
            description=description,
            scope=sc,
        )
        result["generated_at"] = utcnow_obs()
        result["_hint"] = "Policy created. Use thinkneo_policy_evaluate to test it against a request context."
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_policy_list",
        description=(
            "List all active AI governance policies for your organization. "
            "Shows policy name, version, conditions, effect, and scope. "
            "Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_policy_list(
        include_disabled: Annotated[bool, Field(
            description="Include disabled/superseded policy versions"
        )] = False,
    ) -> str:
        token = require_auth()

        policies = list_policies(api_key=token, include_disabled=include_disabled)

        result = {
            "total_policies": len(policies),
            "policies": policies,
            "generated_at": utcnow_obs(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_policy_evaluate",
        description=(
            "Evaluate a request context against all active policies. Returns whether "
            "the request is allowed, which policies were violated, and what effect "
            "each violation triggers. Use this before executing agent actions to enforce "
            "governance rules. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_policy_evaluate(
        context: Annotated[dict, Field(
            description=(
                "Request context to evaluate. Fields: "
                "'model' (e.g., 'gpt-4o'), 'provider' (e.g., 'openai'), "
                "'cost' (e.g., 15000), 'task_type' (e.g., 'legal_analysis'), "
                "'agent_name' (e.g., 'finance-agent'), "
                "'data_classification' (e.g., 'pii', 'public', 'confidential'), "
                "'action' (e.g., 'approve_payment'). "
                "Example: {\"cost\": 15000, \"action\": \"approve_payment\", \"agent_name\": \"finance-bot\"}"
            )
        )],
    ) -> str:
        token = require_auth()

        ctx = context
        if isinstance(ctx, str):
            ctx = json.loads(ctx)

        result = evaluate_policies(api_key=token, context=ctx)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="thinkneo_policy_violations",
        description=(
            "View policy violation history — which policies were triggered, by which "
            "agents, how many blocks/warnings/approvals occurred. Shows unresolved "
            "violations for compliance follow-up. Requires authentication."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_policy_violations(
        days: Annotated[int, Field(description="Number of days to look back (default 30, max 365)")] = 30,
        unresolved_only: Annotated[bool, Field(description="Show only unresolved violations")] = False,
    ) -> str:
        token = require_auth()

        d = min(max(days, 1), 365)
        result = get_violations(api_key=token, days=d, unresolved_only=unresolved_only)
        result["generated_at"] = utcnow_obs()
        return json.dumps(result, indent=2, ensure_ascii=False)
