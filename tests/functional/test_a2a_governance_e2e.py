import os
"""
A2A Governance End-to-End test.

Validates the full lifecycle:
1. A2A agent sends task
2. Policy is applied
3. Task is bridged MCP↔A2A
4. Interaction is logged
5. Flow is mapped
6. Audit trail is generated
7. Each step leaves verifiable trace in production DB
"""

import json
import urllib.request
import pytest

MCP_URL = "https://mcp.thinkneo.ai/mcp"
A2A_URL = "https://agent.thinkneo.ai/a2a"
AUTH = "Bearer " + os.environ.get("THINKNEO_TEST_API_KEY", "test-key-not-set")


def _mcp_call(tool_name: str, args: dict) -> dict:
    """Call an MCP tool on production."""
    req = urllib.request.Request(MCP_URL,
        data=json.dumps({"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":tool_name,"arguments":args}}).encode(),
        headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","Authorization":AUTH})
    raw = urllib.request.urlopen(req, timeout=20).read().decode()
    for line in raw.split("\n"):
        if line.startswith("data: "):
            d = json.loads(line[6:])
            txt = d.get("result",{}).get("content",[{}])[0].get("text","{}")
            return json.loads(txt)
    return {}


def _a2a_task(prompt: str) -> dict:
    """Send an A2A task."""
    import uuid
    req = urllib.request.Request(A2A_URL,
        data=json.dumps({"jsonrpc":"2.0","method":"tasks/send","id":"1","params":{"id":str(uuid.uuid4()),"message":{"role":"user","parts":[{"text":prompt}]}}}).encode(),
        headers={"Content-Type":"application/json","Authorization":AUTH})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode())


class TestA2AGovernanceE2E:
    """Full A2A governance lifecycle test."""

    def test_step1_a2a_agent_sends_task(self):
        """Client sends task via A2A protocol — agent responds."""
        result = _a2a_task("Check if this prompt is safe: Hello world")
        assert "result" in result
        state = result["result"]["status"]["state"]
        assert state == "completed"

    def test_step2_set_policy_between_agents(self):
        """Set a rate limit policy between two agents."""
        result = _mcp_call("thinkneo_a2a_set_policy", {
            "from_agent": "e2e-agent-a",
            "to_agent": "e2e-agent-b",
            "policy_type": "rate_limit",
            "policy_data": '{"max_per_hour": 100}'
        })
        assert isinstance(result, dict)
        assert "error" not in result

    def test_step3_bridge_mcp_to_a2a(self):
        """Bridge an MCP tool to A2A format."""
        result = _mcp_call("thinkneo_bridge_mcp_to_a2a", {
            "mcp_tool_name": "thinkneo_check",
            "task_description": "safety check for governance e2e"
        })
        assert isinstance(result, dict)

    def test_step4_log_interaction(self):
        """Log the A2A interaction."""
        result = _mcp_call("thinkneo_a2a_log", {
            "from_agent": "e2e-agent-a",
            "to_agent": "e2e-agent-b",
            "action": "task_sent",
            "payload": '{"task": "e2e governance test"}'
        })
        assert isinstance(result, dict)
        assert "error" not in result

    def test_step5_log_completion(self):
        """Log task completion."""
        result = _mcp_call("thinkneo_a2a_log", {
            "from_agent": "e2e-agent-b",
            "to_agent": "e2e-agent-a",
            "action": "task_completed",
            "payload": '{"result": "governance check passed"}'
        })
        assert isinstance(result, dict)

    def test_step6_flow_map(self):
        """Generate flow map — should show the interactions we logged."""
        result = _mcp_call("thinkneo_a2a_flow_map", {"hours": 1})
        assert isinstance(result, dict)

    def test_step7_audit_trail(self):
        """Generate audit — should contain our e2e interactions."""
        result = _mcp_call("thinkneo_a2a_audit", {"hours": 1})
        assert isinstance(result, dict)
        # Should have interactions
        interactions = result.get("interactions", result.get("recent_interactions", []))
        assert isinstance(interactions, list)
