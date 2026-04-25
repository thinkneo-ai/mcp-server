"""
OpenAI provider compatibility tests.

Models verified 2026-04-25:
- gpt-4o (flagship)
- gpt-4o-mini (cost-efficient)
- gpt-4.1 (improved instruction following)

Source: https://developers.openai.com/api/docs/models
"""

import json
import httpx
import pytest
from .conftest import get_key, measure_call, log_latency, validate_chat_response

API_URL = "https://api.openai.com/v1/chat/completions"

MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1"]


@pytest.fixture
def api_key():
    return get_key("OPENAI_API_KEY")


def _chat(api_key: str, model: str, text: str = "Say 'OK' and nothing else.") -> tuple[dict, float]:
    def call():
        resp = httpx.post(API_URL, json={
            "model": model,
            "max_tokens": 50,
            "messages": [
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user", "content": text},
            ],
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, timeout=30)
        resp.raise_for_status()
        return resp.json()
    return measure_call(call)


@pytest.mark.parametrize("model", MODELS)
def test_chat_completion(api_key, model):
    data, latency = _chat(api_key, model)
    validate_chat_response(data, "openai")
    log_latency(model, "chat", latency)


def test_streaming(api_key):
    chunks = 0
    start = __import__("time").perf_counter()
    with httpx.stream("POST", API_URL, json={
        "model": "gpt-4o-mini",
        "max_tokens": 50,
        "stream": True,
        "messages": [{"role": "user", "content": "Say hello."}],
    }, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }, timeout=30) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                chunks += 1
    latency = (__import__("time").perf_counter() - start) * 1000
    assert chunks >= 2
    log_latency("gpt-4o-mini", "streaming", latency)


def test_tool_use(api_key):
    data, latency = measure_call(lambda: httpx.post(API_URL, json={
        "model": "gpt-4o-mini",
        "max_tokens": 200,
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            },
        }],
        "messages": [{"role": "user", "content": "Weather in Tokyo?"}],
    }, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }, timeout=30).json())
    assert "choices" in data
    log_latency("gpt-4o-mini", "tool_use", latency)


def test_response_has_usage(api_key):
    data, _ = _chat(api_key, "gpt-4o-mini")
    usage = data.get("usage", {})
    assert "prompt_tokens" in usage
    assert "completion_tokens" in usage
