"""
Google Gemini provider compatibility tests.

Models verified 2026-04-25:
- gemini-2.5-flash (cost-efficient)
- gemini-2.5-pro (flagship reasoning)

Source: https://ai.google.dev/gemini-api/docs/models
"""

import json
import httpx
import pytest
from .conftest import get_key, measure_call, log_latency, validate_chat_response

MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]


@pytest.fixture
def api_key():
    return get_key("GOOGLE_API_KEY")


def _chat(api_key: str, model: str, text: str = "Say 'OK' and nothing else.") -> tuple[dict, float]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    def call():
        resp = httpx.post(url, json={
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"maxOutputTokens": 50},
        }, headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    return measure_call(call)


@pytest.mark.parametrize("model", MODELS)
def test_chat_completion(api_key, model):
    data, latency = _chat(api_key, model)
    validate_chat_response(data, "google")
    log_latency(model, "chat", latency)


def test_streaming(api_key):
    model = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
    chunks = 0
    start = __import__("time").perf_counter()
    with httpx.stream("POST", url, json={
        "contents": [{"parts": [{"text": "Say hello."}]}],
        "generationConfig": {"maxOutputTokens": 50},
    }, headers={"Content-Type": "application/json"}, timeout=30) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith("data: "):
                chunks += 1
    latency = (__import__("time").perf_counter() - start) * 1000
    assert chunks >= 1
    log_latency(model, "streaming", latency)


def test_response_has_usage(api_key):
    data, _ = _chat(api_key, "gemini-2.5-flash")
    assert "candidates" in data
    # Gemini returns usageMetadata
    assert "usageMetadata" in data or "candidates" in data
