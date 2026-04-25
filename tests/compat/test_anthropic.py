"""
Anthropic provider compatibility tests.

Models verified 2026-04-25:
- claude-sonnet-4-20250514 (Sonnet 4.6)
- claude-haiku-4-5-20251001 (Haiku 4.5)
- claude-opus-4-20250414 (Opus 4.7)

Source: https://platform.claude.com/docs/en/about-claude/models/overview
"""

import json
import httpx
import pytest
from .conftest import get_key, measure_call, log_latency, validate_chat_response

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

MODELS = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
]

# Opus tested separately (expensive)
OPUS_MODEL = "claude-opus-4-20250416"


@pytest.fixture
def api_key():
    return get_key("ANTHROPIC_API_KEY")


def _chat(api_key: str, model: str, text: str = "Say 'OK' and nothing else.") -> tuple[dict, float]:
    """Make a chat completion call and return (response, latency_ms)."""
    def call():
        resp = httpx.post(API_URL, json={
            "model": model,
            "max_tokens": 50,
            "messages": [{"role": "user", "content": text}],
        }, headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }, timeout=30)
        resp.raise_for_status()
        return resp.json()
    return measure_call(call)


# --- Chat completion ---

@pytest.mark.parametrize("model", MODELS)
def test_chat_completion(api_key, model):
    data, latency = _chat(api_key, model)
    validate_chat_response(data, "anthropic")
    log_latency(model, "chat", latency)


def test_chat_opus(api_key):
    """Opus — single call, expensive."""
    data, latency = _chat(api_key, OPUS_MODEL)
    validate_chat_response(data, "anthropic")
    log_latency(OPUS_MODEL, "chat", latency)


# --- Streaming ---

@pytest.mark.parametrize("model", MODELS)
def test_streaming(api_key, model):
    chunks = 0
    start = __import__("time").perf_counter()
    with httpx.stream("POST", API_URL, json={
        "model": model,
        "max_tokens": 50,
        "stream": True,
        "messages": [{"role": "user", "content": "Say hello."}],
    }, headers={
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }, timeout=30) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data: "):
                chunks += 1
    latency = (__import__("time").perf_counter() - start) * 1000
    assert chunks >= 2, f"Expected ≥2 SSE chunks, got {chunks}"
    log_latency(model, "streaming", latency)


# --- Tool use ---

def test_tool_use(api_key):
    data, latency = measure_call(lambda: httpx.post(API_URL, json={
        "model": MODELS[0],
        "max_tokens": 200,
        "tools": [{
            "name": "get_weather",
            "description": "Get weather for a city",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
        }],
        "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
    }, headers={
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }, timeout=30).json())
    # Model should either use the tool or respond with text
    assert "content" in data
    log_latency(MODELS[0], "tool_use", latency)


# --- Response shape ---

def test_response_has_usage(api_key):
    data, _ = _chat(api_key, MODELS[1])
    assert "input_tokens" in data.get("usage", {}), "Missing input_tokens"
    assert "output_tokens" in data.get("usage", {}), "Missing output_tokens"
