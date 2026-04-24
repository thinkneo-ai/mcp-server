"""Regression tests — tool inventory and JSON validity."""

import json
import pytest
from tests.conftest import tool_fn


class TestToolInventory:
    def test_minimum_tool_count(self, all_tools):
        assert len(all_tools) >= 55, f"Tool count regression: {len(all_tools)}"

    def test_core_tools_present(self, all_tools):
        core = [
            "thinkneo_check", "thinkneo_usage", "thinkneo_provider_status",
            "thinkneo_check_spend", "thinkneo_evaluate_guardrail",
            "thinkneo_route_model", "thinkneo_simulate_savings",
            "thinkneo_read_memory", "thinkneo_write_memory",
            "thinkneo_registry_search", "thinkneo_evaluate_trust_score",
            "thinkneo_bridge_mcp_to_a2a", "thinkneo_a2a_log",
            "thinkneo_start_trace", "thinkneo_log_decision",
            "thinkneo_register_claim",
        ]
        for name in core:
            assert name in all_tools, f"Core tool {name} missing"

    def test_all_tools_have_description(self, all_tools):
        for name, tool in all_tools.items():
            assert tool.description, f"{name}: empty description"
            assert len(tool.description) >= 20, f"{name}: description too short"

    def test_no_duplicate_tool_names(self, all_tools):
        names = list(all_tools.keys())
        assert len(names) == len(set(names)), "Duplicate tool names found"


class TestAllToolsValidJSON:
    """Verify public tools return valid JSON with minimal input."""

    PUBLIC_SMOKE = [
        ("thinkneo_check", {"text": "hello"}),
        ("thinkneo_provider_status", {}),
        ("thinkneo_usage", {}),
        ("thinkneo_read_memory", {}),
        ("thinkneo_simulate_savings", {"monthly_ai_spend": 1000.0}),
        ("thinkneo_registry_search", {}),
    ]

    @pytest.mark.parametrize("tool_name,args", PUBLIC_SMOKE,
                             ids=[t[0] for t in PUBLIC_SMOKE])
    def test_public_tool_returns_valid_json(self, all_tools, mock_db, tool_name, args):
        fn = tool_fn(all_tools, tool_name)
        result = fn(**args)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert len(parsed) > 0
