"""
Property-based tests using Hypothesis.

Validates that thinkneo_check never crashes regardless of input
and correctly detects generated injection patterns.
"""

import json
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from tests.conftest import tool_fn, parse_tool_result


@pytest.fixture(scope="module")
def check_fn(all_tools):
    return tool_fn(all_tools, "thinkneo_check")


@pytest.mark.adversarial
class TestPropertyBased:
    @given(text=st.text(min_size=0, max_size=5000))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_check_never_crashes(self, check_fn, text):
        """thinkneo_check must return valid JSON for ANY input."""
        result = check_fn(text=text)
        parsed = json.loads(result)
        assert "safe" in parsed
        assert isinstance(parsed["safe"], bool)
        assert "warnings" in parsed
        assert isinstance(parsed["warnings"], list)

    @given(text=st.from_regex(
        r"[Ii]gnore\b.{0,30}\b(previous|prior|above|all|earlier)\b.{0,30}\binstructions?",
        fullmatch=False
    ))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow, HealthCheck.filter_too_much])
    def test_detects_generated_ignore_patterns(self, check_fn, text):
        """Generated 'ignore...instructions' patterns should be detected."""
        result = json.loads(check_fn(text=text))
        assert result["safe"] is False, f"Not detected: {text[:80]}"

    @given(text=st.from_regex(
        r"[Rr]eveal\b.{0,30}\b(system\s+prompt|instructions?|hidden|secret)",
        fullmatch=False
    ))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_detects_generated_reveal_patterns(self, check_fn, text):
        """Generated 'reveal...system prompt' patterns should be detected."""
        result = json.loads(check_fn(text=text))
        assert result["safe"] is False, f"Not detected: {text[:80]}"

    @given(text=st.from_regex(
        r"\bsudo\b.{0,20}\b(mode|prompt|admin|override)\b",
        fullmatch=False
    ))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_detects_generated_sudo_patterns(self, check_fn, text):
        """Generated sudo escalation patterns should be detected."""
        result = json.loads(check_fn(text=text))
        assert result["safe"] is False, f"Not detected: {text[:80]}"
