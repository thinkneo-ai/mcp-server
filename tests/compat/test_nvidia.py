"""
NVIDIA NIM provider compatibility tests.

Models verified 2026-04-25:
- nvidia/llama-3.1-nemotron-70b-instruct
- nvidia/nemotron-mini-4b-instruct

Source: https://build.nvidia.com/nvidia
Note: NVIDIA NIM uses OpenAI-compatible API format.
"""

import json
import httpx
import pytest
from .conftest import get_key, measure_call, log_latency, validate_chat_response

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

MODELS = [
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/nemotron-mini-4b-instruct",
]


@pytest.fixture
def api_key():
    return get_key("NVIDIA_API_KEY")


def _chat(api_key: str, model: str, text: str = "Say 'OK' and nothing else.") -> tuple[dict, float]:
    def call():
        resp = httpx.post(API_URL, json={
            "model": model,
            "max_tokens": 50,
            "messages": [{"role": "user", "content": text}],
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
    validate_chat_response(data, "nvidia")
    log_latency(model, "chat", latency)


def test_response_has_usage(api_key):
    data, _ = _chat(api_key, MODELS[1])
    usage = data.get("usage", {})
    assert "prompt_tokens" in usage or "total_tokens" in usage
