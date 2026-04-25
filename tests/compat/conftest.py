"""
Provider compatibility test fixtures.

Provides httpx client, latency capture, and response validation helpers.
"""

import os
import time
import httpx
import pytest


def get_key(env_var: str) -> str:
    """Get API key from environment, skip test if not set."""
    key = os.environ.get(env_var, "")
    if not key:
        pytest.skip(f"{env_var} not set")
    return key


def measure_call(fn, *args, **kwargs):
    """Call fn and return (result, latency_ms)."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    latency = (time.perf_counter() - start) * 1000
    return result, latency


def log_latency(model: str, test_type: str, latency_ms: float):
    """Log latency to stdout (captured by CI as artifact)."""
    print(f"  LATENCY | {model} | {test_type} | {latency_ms:.0f}ms")


def validate_chat_response(data: dict, provider: str):
    """Validate that a chat completion response has expected structure."""
    if provider == "anthropic":
        assert "content" in data, f"Missing 'content' in Anthropic response"
        assert data.get("role") == "assistant"
        assert "usage" in data
        assert "input_tokens" in data["usage"]
    elif provider in ("openai", "nvidia"):
        assert "choices" in data, f"Missing 'choices' in {provider} response"
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]
        assert "usage" in data
    elif provider == "google":
        assert "candidates" in data, f"Missing 'candidates' in Google response"
        assert len(data["candidates"]) > 0
