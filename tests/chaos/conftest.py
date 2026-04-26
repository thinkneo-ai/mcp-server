"""
Chaos Engineering test fixtures.

Manages the chaos Docker Compose stack, toxiproxy proxies, and wiremock stubs.
Tests in this package use live containers — they are NOT unit tests.
"""

import json
import os
import subprocess
import time

import httpx
import pytest

COMPOSE_FILE = os.path.join(os.path.dirname(__file__), "docker-compose-chaos.yml")
GATEWAY_URL = "http://localhost:18081"
TOXIPROXY_API = "http://localhost:8474"
WIREMOCK_API = "http://localhost:18089"

AUTH_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Authorization": "Bearer chaos-test-key",
}
PUBLIC_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


# ---------------------------------------------------------------------------
# Stack lifecycle
# ---------------------------------------------------------------------------

def _wait_for(url: str, timeout: int = 90):
    """Wait for a URL to return a non-5xx response."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"{url} not ready after {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def chaos_stack():
    """Boot entire chaos stack, yield, tear down."""
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build"],
        check=True,
        capture_output=True,
    )
    _wait_for(f"{GATEWAY_URL}/mcp/docs", timeout=120)
    _wait_for(f"{TOXIPROXY_API}/proxies", timeout=30)
    _wait_for(f"{WIREMOCK_API}/__admin/mappings", timeout=30)
    yield
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------

def call_tool(tool_name: str, args: dict | None = None, auth: bool = True) -> httpx.Response:
    """Call an MCP tool on the chaos gateway."""
    headers = AUTH_HEADERS if auth else PUBLIC_HEADERS
    return httpx.post(
        f"{GATEWAY_URL}/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": "1",
            "params": {"name": tool_name, "arguments": args or {}},
        },
        headers=headers,
        timeout=30,
    )


def parse_sse_result(resp: httpx.Response) -> dict:
    """Parse SSE response from MCP tool call.

    Returns the parsed JSON from the first data line's content text,
    or a dict with {"raw": text} if not JSON, or {} if nothing found.
    """
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            try:
                d = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            # Handle error responses
            error = d.get("error")
            if error:
                return {"error": error}
            content = d.get("result", {}).get("content", [{}])
            if content:
                text = content[0].get("text", "{}")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}
    return {}


def gateway_pid() -> str:
    """Get the PID of the gateway container main process."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Pid}}", "thinkneo-chaos-gateway"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def gateway_status() -> str:
    """Get the container status (running/exited/etc.)."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", "thinkneo-chaos-gateway"],
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def gateway_logs(tail: int = 100) -> str:
    """Get recent gateway container logs."""
    result = subprocess.run(
        ["docker", "logs", "--tail", str(tail), "thinkneo-chaos-gateway"],
        capture_output=True, text=True,
    )
    return result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Container control
# ---------------------------------------------------------------------------

def stop_container(name: str):
    subprocess.run(["docker", "stop", name], capture_output=True, timeout=30)


def start_container(name: str):
    subprocess.run(["docker", "start", name], capture_output=True, timeout=30)


# ---------------------------------------------------------------------------
# toxiproxy helpers
# ---------------------------------------------------------------------------

def toxiproxy_create_proxy(name: str, listen: str, upstream: str):
    """Create a toxiproxy proxy. Idempotent — ignores conflict."""
    try:
        httpx.post(f"{TOXIPROXY_API}/proxies", json={
            "name": name, "listen": listen, "upstream": upstream,
        }, timeout=5)
    except Exception:
        pass


def toxiproxy_add_toxic(proxy_name: str, toxic_type: str, attributes: dict):
    """Add a toxic to a proxy (latency, timeout, bandwidth, etc.)."""
    httpx.post(f"{TOXIPROXY_API}/proxies/{proxy_name}/toxics", json={
        "type": toxic_type,
        "attributes": attributes,
    }, timeout=5)


def toxiproxy_remove_all_toxics(proxy_name: str):
    """Remove all toxics from a proxy."""
    try:
        toxics = httpx.get(f"{TOXIPROXY_API}/proxies/{proxy_name}/toxics", timeout=5).json()
        for t in toxics:
            httpx.delete(f"{TOXIPROXY_API}/proxies/{proxy_name}/toxics/{t['name']}", timeout=5)
    except Exception:
        pass


def toxiproxy_disable_proxy(proxy_name: str):
    """Disable a proxy (cut connection)."""
    try:
        httpx.post(f"{TOXIPROXY_API}/proxies/{proxy_name}", json={
            "enabled": False,
        }, timeout=5)
    except Exception:
        pass


def toxiproxy_enable_proxy(proxy_name: str):
    """Re-enable a proxy."""
    try:
        httpx.post(f"{TOXIPROXY_API}/proxies/{proxy_name}", json={
            "enabled": True,
        }, timeout=5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# wiremock helpers
# ---------------------------------------------------------------------------

def wiremock_stub(url_pattern: str, status: int, body: str = "",
                  headers: dict | None = None, delay_ms: int = 0):
    """Create a wiremock stub mapping."""
    mapping: dict = {
        "request": {"method": "POST", "urlPathPattern": url_pattern},
        "response": {
            "status": status,
            "body": body,
            "fixedDelayMilliseconds": delay_ms,
        },
    }
    if headers:
        mapping["response"]["headers"] = headers
    httpx.post(f"{WIREMOCK_API}/__admin/mappings", json=mapping, timeout=5)


def wiremock_reset():
    """Clear all wiremock stubs."""
    try:
        httpx.post(f"{WIREMOCK_API}/__admin/mappings/reset", timeout=5)
    except Exception:
        pass
