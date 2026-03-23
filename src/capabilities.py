"""
ThinkNEO MCP — Prompts and Resources
Registers governance prompts and documentation resources.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(
        name="thinkneo_governance_audit",
        title="AI Governance Audit",
        description=(
            "Run a full governance audit for a workspace: check budget status, "
            "list active alerts, and review compliance readiness."
        ),
    )
    def thinkneo_governance_audit(workspace: str) -> list[dict]:
        """
        Args:
            workspace: Workspace name or ID to audit
        """
        return [
            {
                "role": "user",
                "content": (
                    f"Please run a full AI governance audit for the workspace '{workspace}'. "
                    f"Use the following tools in sequence:\n"
                    f"1. thinkneo_get_budget_status(workspace='{workspace}') — check spend vs limits\n"
                    f"2. thinkneo_list_alerts(workspace='{workspace}', severity='all') — review active alerts\n"
                    f"3. thinkneo_get_compliance_status(workspace='{workspace}', framework='general') — check governance score\n"
                    f"4. thinkneo_check_spend(workspace='{workspace}', period='this-month', group_by='provider') — cost breakdown\n\n"
                    f"Summarize the findings with: overall governance health, top risks, and recommended next actions."
                ),
            }
        ]

    @mcp.prompt(
        name="thinkneo_policy_preflight",
        title="Policy Pre-flight Check",
        description=(
            "Pre-flight check before switching to a new AI model or provider: "
            "verify it's allowed by workspace policy and evaluate guardrail compliance."
        ),
    )
    def thinkneo_policy_preflight(
        workspace: str,
        provider: str,
        model: str,
        sample_prompt: str = "",
    ) -> list[dict]:
        """
        Args:
            workspace: Workspace name or ID
            provider: AI provider to evaluate (e.g., openai, anthropic)
            model: Model name to evaluate (e.g., gpt-4o, claude-sonnet-4-6)
            sample_prompt: Optional sample prompt to evaluate against guardrails
        """
        steps = (
            f"1. thinkneo_check_policy(workspace='{workspace}', provider='{provider}', model='{model}') "
            f"— verify this model/provider is permitted\n"
        )
        if sample_prompt:
            steps += (
                f"2. thinkneo_evaluate_guardrail(workspace='{workspace}', "
                f"text='{sample_prompt[:200]}', guardrail_mode='enforce') "
                f"— check sample prompt against policies\n"
            )

        return [
            {
                "role": "user",
                "content": (
                    f"Run a pre-flight policy check before using {provider}/{model} in workspace '{workspace}'.\n\n"
                    + steps
                    + "\nReport whether it's safe to proceed and flag any blockers."
                ),
            }
        ]


def register_resources(mcp: FastMCP) -> None:
    @mcp.resource(
        "thinkneo://docs/getting-started",
        name="ThinkNEO Getting Started",
        title="ThinkNEO Getting Started Guide",
        description="Quick-start guide for connecting your AI applications to the ThinkNEO control plane.",
        mime_type="text/plain",
    )
    def getting_started() -> str:
        return """\
ThinkNEO Control Plane — Getting Started
==========================================

ThinkNEO sits between your AI applications and providers, enforcing governance on every request.

## 1. Get Your API Key
Request access at: https://thinkneo.ai/talk-sales
Or email: hello@thinkneo.ai

## 2. Connect via MCP
Add to your Claude Desktop config (~/.claude/claude_desktop_config.json):

  {
    "mcpServers": {
      "thinkneo": {
        "url": "https://mcp.thinkneo.ai/mcp",
        "headers": {
          "Authorization": "Bearer <YOUR_THINKNEO_API_KEY>"
        }
      }
    }
  }

## 3. Available Tools (authenticated)
- thinkneo_check_spend        — AI cost by provider/model/team
- thinkneo_evaluate_guardrail — Pre-flight prompt safety evaluation
- thinkneo_check_policy       — Verify model/provider is allowed
- thinkneo_get_budget_status  — Budget utilization and enforcement
- thinkneo_list_alerts        — Active alerts and incidents
- thinkneo_get_compliance_status — SOC2/GDPR/HIPAA readiness

## 4. Public Tools (no auth required)
- thinkneo_provider_status    — Real-time AI provider health
- thinkneo_schedule_demo      — Book a demo with the team

## Links
- Platform: https://thinkneo.ai
- Docs:     https://thinkneo.ai/developers
- Trust:    https://thinkneo.ai/trust
- Support:  hello@thinkneo.ai
"""

    @mcp.resource(
        "thinkneo://docs/supported-providers",
        name="Supported AI Providers",
        title="ThinkNEO Supported AI Providers",
        description="List of AI providers supported by the ThinkNEO gateway with available models.",
        mime_type="application/json",
    )
    def supported_providers() -> dict:
        return {
            "providers": [
                {"id": "openai", "name": "OpenAI", "models": ["gpt-4o", "gpt-4o-mini", "o1", "o3"]},
                {"id": "anthropic", "name": "Anthropic", "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]},
                {"id": "google", "name": "Google AI", "models": ["gemini-2.0-flash", "gemini-1.5-pro"]},
                {"id": "mistral", "name": "Mistral AI", "models": ["mistral-large-2", "mistral-medium-3", "codestral"]},
                {"id": "xai", "name": "xAI", "models": ["grok-3", "grok-3-mini"]},
                {"id": "cohere", "name": "Cohere", "models": ["command-r-plus", "command-r"]},
                {"id": "together", "name": "Together AI", "models": ["meta-llama/Llama-3-70b-instruct"]},
                {"id": "nvidia", "name": "NVIDIA NIM", "models": ["llama-3.1-70b-instruct", "mistral-7b-instruct"]},
                {"id": "deepseek", "name": "DeepSeek", "models": ["deepseek-chat", "deepseek-reasoner"]},
            ],
            "docs": "https://thinkneo.ai/developers",
        }
