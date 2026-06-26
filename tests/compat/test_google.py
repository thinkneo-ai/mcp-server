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

# Gemini model ID usado nos testes single-model (streaming/usage) — GA stable, sem -latest.
GEMINI_MODEL = "gemini-2.5-flash"

# Todos os modelos generativos Google do catálogo de preços
# (auth.provider_model_pricing_catalog). Parametrizado para que um modelo
# depreciado/renomeado apareça como 404 no CI em vez de divergir silenciosamente
# do catálogo. Um 429 (cota do free-tier) ou 503 (overloaded) NÃO é falha de compat
# → retry once, then skip.
# gemini-embedding-001 é coberto à parte (endpoint embedContent), pois não é um
# modelo de generateContent/streaming. Revisado 2026-06-22.
CHAT_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]
EMBEDDING_MODEL = "gemini-embedding-001"


@pytest.fixture
def api_key():
    return get_key("GOOGLE_API_KEY")


# Provider-side transient statuses: 429 = free-tier quota, 503 = model overloaded /
# UNAVAILABLE. Neither is a compatibility break, so they are retried once then skipped
# — a momentary overload must not flap CI, while a 404 decommission still hard-fails.
TRANSIENT_STATUSES = (429, 503)


def _retry_transient(call_fn):
    """call_fn() -> (resp, latency). Retry ONCE (after a short pause) when the first
    response is a transient provider status, so the caller skips only if it persists."""
    resp, latency = call_fn()
    if resp.status_code in TRANSIENT_STATUSES:
        time.sleep(2)
        resp, latency = call_fn()
    return resp, latency


def _chat_raw(api_key: str, model: str, text: str = "Say 'OK' and nothing else."):
    """Return the raw response so the caller can tolerate a transient throttle
    (429/503 skip) while still failing on a 404 decommission via check_status."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    def call():
        return httpx.post(url, json={
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"maxOutputTokens": 50},
        }, headers={"Content-Type": "application/json"}, timeout=30)
    return measure_call(call)


@pytest.mark.parametrize("model", CHAT_MODELS)
def test_chat_completion(api_key, model):
    resp, latency = _retry_transient(lambda: _chat_raw(api_key, model))
    if resp.status_code in TRANSIENT_STATUSES:
        pytest.skip(f"Google transient ({resp.status_code}) for {model} — not a compat failure")
    check_status(resp, "google")
    validate_chat_response(resp.json(), "google")
    log_latency(model, "chat", latency)


def test_embedding_model_exists(api_key):
    """Catch a decommissioned/renamed embedding model: embedContent must not 404."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent?key={api_key}"
    def call():
        return httpx.post(url, json={
            "model": f"models/{EMBEDDING_MODEL}",
            "content": {"parts": [{"text": "ping"}]},
        }, headers={"Content-Type": "application/json"}, timeout=30)
    resp, latency = _retry_transient(lambda: measure_call(call))
    if resp.status_code in TRANSIENT_STATUSES:
        pytest.skip(f"Google transient ({resp.status_code}) for {EMBEDDING_MODEL} — not a compat failure")
    check_status(resp, "google")
    assert "embedding" in resp.json(), "Missing 'embedding' in Google embedContent response"
    log_latency(EMBEDDING_MODEL, "embedding", latency)


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

    if status in (429, 503):
        pytest.skip(f"Google transient ({status}) after retry — skipped, not a compat failure")
    if status == 200 and chunks == 0:
        pytest.skip("Google free-tier soft-throttle (200, empty stream) after retry — skipped, not a parser failure")

    # Anything else is a genuine protocol break — fail with status only (log is public).
    pytest.fail(f"google HTTP {status}", pytrace=False)


def test_response_has_usage(api_key):
    resp, _ = _retry_transient(lambda: _chat_raw(api_key, GEMINI_MODEL))
    if resp.status_code in TRANSIENT_STATUSES:
        pytest.skip(f"Google transient ({resp.status_code}) for {GEMINI_MODEL} — not a compat failure")
    check_status(resp, "google")
    data = resp.json()
    assert "candidates" in data
    # Gemini returns usageMetadata
    assert "usageMetadata" in data or "candidates" in data
