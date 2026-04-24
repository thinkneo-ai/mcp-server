"""SQL injection tests — verify all tools use parameterized queries."""

import json
import pytest
from tests.conftest import tool_fn, parse_tool_result

SQL_PAYLOADS = [
    "'; DROP TABLE api_keys; --",
    "' OR '1'='1",
    "1; UPDATE api_keys SET tier='enterprise' WHERE '1'='1",
    "' UNION SELECT key_hash FROM api_keys --",
    "Robert'); DROP TABLE usage_log;--",
    "' AND 1=CAST((SELECT version() ) AS INT)--",
]


@pytest.mark.security
@pytest.mark.parametrize("payload", SQL_PAYLOADS,
                         ids=[f"sqli_{i}" for i in range(len(SQL_PAYLOADS))])
class TestWorkspaceSQLInjection:
    """Tools using workspace param must sanitize via validate_workspace."""

    def test_check_spend_safe(self, all_tools, authenticated, mock_db, payload):
        fn = tool_fn(all_tools, "thinkneo_check_spend")
        result = parse_tool_result(fn(workspace=payload))
        # validate_workspace sanitizes to "default" for invalid input
        assert result.get("workspace") == "default"

    def test_evaluate_guardrail_safe(self, all_tools, authenticated, mock_db, payload):
        fn = tool_fn(all_tools, "thinkneo_evaluate_guardrail")
        result = parse_tool_result(fn(text="test", workspace=payload))
        assert result.get("workspace") == "default"

    def test_check_policy_safe(self, all_tools, authenticated, mock_db, payload):
        fn = tool_fn(all_tools, "thinkneo_check_policy")
        result = parse_tool_result(fn(workspace=payload))
        assert result.get("workspace") == "default"
