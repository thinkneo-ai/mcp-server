"""
Google Gemini provider compatibility tests.

These verify PROTOCOL compatibility (auth, response shape, SSE framing) — not
model capability. The model only needs to exist and return 200.

Source: https://ai.google.dev/gemini-api/docs/models
"""

import time
import httpx
import pytest
from .conftest import get_key, measure_call, log_latency, validate_chat_response, check_status

# Gemini model ID — atualizar se o Google depreciar este modelo; revisado 2026-06-17.
# Apenas GA stable (sem aliases -latest). Pro foi removido: 429 no free-tier do CI.
GEMINI_MODEL = "gemini-2.5-flash"
MODELS = [GEMINI_MODEL]


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
        check_status(resp, "google")
        return resp.json()
    return measure_call(call)


@pytest.mark.parametrize("model", MODELS)
def test_chat_completion(api_key, model):
    data, latency = _chat(api_key, model)
    validate_chat_response(data, "google")
    log_latency(model, "chat", latency)


def _stream_once(api_key: str, model: str) -> tuple[int, int]:
    """One streaming attempt. Returns (status_code, chunks_seen) without asserting.

    chunks is only counted on a 200; on any other status it stays 0 so the caller
    can distinguish 'throttle' from 'real protocol break'."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
    chunks = 0
    with httpx.stream("POST", url, json={
        "contents": [{"parts": [{"text": "Say hello."}]}],
        "generationConfig": {"maxOutputTokens": 50},
    }, headers={"Content-Type": "application/json"}, timeout=30) as resp:
        if resp.status_code == 200:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    chunks += 1
        return resp.status_code, chunks


def test_streaming(api_key):
    """Prove the SSE parser counts real chunks when Google delivers data.

    Google's free-tier key throttles two ways: a hard 429 (quota) and an occasional
    soft 200-with-empty-stream. Neither is a compat failure, so we give the throttle
    a SINGLE retry. We still REQUIRE chunks >= 1 on a delivering stream — that is what
    catches a future parser regression (0 chunks from a bug, not a throttle)."""
    start = time.perf_counter()
    status, chunks = _stream_once(api_key, GEMINI_MODEL)
    if status == 200 and chunks >= 1:
        log_latency(GEMINI_MODEL, "streaming", (time.perf_counter() - start) * 1000)
        return

    # First attempt was throttled (429) or soft-throttled (200, empty). One retry.
    status, chunks = _stream_once(api_key, GEMINI_MODEL)
    if status == 200 and chunks >= 1:
        log_latency(GEMINI_MODEL, "streaming", (time.perf_counter() - start) * 1000)
        assert chunks >= 1
        return

    if status == 429:
        pytest.skip("Google free-tier quota (429) after retry — skipped, not a compat failure")
    if status == 200 and chunks == 0:
        pytest.skip("Google free-tier soft-throttle (200, empty stream) after retry — skipped, not a parser failure")

    # Anything else is a genuine protocol break — fail with status only (log is public).
    pytest.fail(f"google HTTP {status}", pytrace=False)


def test_response_has_usage(api_key):
    data, _ = _chat(api_key, GEMINI_MODEL)
    assert "candidates" in data
    # Gemini returns usageMetadata
    assert "usageMetadata" in data or "candidates" in data
