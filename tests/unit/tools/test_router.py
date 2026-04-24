"""
Deep unit tests for Smart Router tools.

Tests model routing logic, quality thresholds, and savings calculation.
"""

import json
import pytest
from tests.conftest import tool_fn, parse_tool_result


@pytest.fixture
def route_fn(all_tools, authenticated, mock_db):
    return tool_fn(all_tools, "thinkneo_route_model")


@pytest.fixture
def simulate_fn(all_tools, mock_db):
    return tool_fn(all_tools, "thinkneo_simulate_savings")


class TestRouteModel:
    def test_returns_recommendation(self, route_fn):
        result = parse_tool_result(route_fn(task_type="chat"))
        assert "recommended_model" in result
        assert "provider" in result
        assert "cost_estimate_usd" in result

    def test_quality_threshold_respected(self, route_fn):
        result = parse_tool_result(route_fn(task_type="code_generation", quality_threshold=95))
        assert result["quality_score"] >= 95

    def test_invalid_task_type_defaults_to_chat(self, route_fn):
        result = parse_tool_result(route_fn(task_type="nonexistent_task"))
        assert result["task_type"] == "chat"

    def test_returns_alternatives(self, route_fn):
        result = parse_tool_result(route_fn(task_type="summarization"))
        assert "alternatives" in result
        assert isinstance(result["alternatives"], list)

    def test_savings_calculated(self, route_fn):
        result = parse_tool_result(route_fn(task_type="chat", quality_threshold=85))
        assert "savings_pct" in result
        assert result["savings_pct"] >= 0


class TestSimulateSavings:
    def test_returns_savings(self, simulate_fn):
        result = parse_tool_result(simulate_fn(monthly_ai_spend=10000.0))
        assert "estimated_monthly_savings" in result
        assert result["estimated_monthly_savings"] >= 0

    def test_zero_spend_rejected(self, simulate_fn):
        result = parse_tool_result(simulate_fn(monthly_ai_spend=0))
        assert "error" in result

    def test_negative_spend_rejected(self, simulate_fn):
        result = parse_tool_result(simulate_fn(monthly_ai_spend=-100))
        assert "error" in result

    def test_large_spend_capped(self, simulate_fn):
        result = parse_tool_result(simulate_fn(monthly_ai_spend=999_999_999))
        assert isinstance(result, dict)
        assert "error" not in result
