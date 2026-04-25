"""
Chaos Engineering test fixtures.

Manages the chaos Docker Compose stack, toxiproxy proxies, and wiremock stubs.
"""

import os
import subprocess
import time
import json
import pytest
import httpx

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


def _wait_for(url: str, timeout: int = 90):
    """Wait for a URL to return 200."""
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


def call_tool(tool_name: str, args: dict = {}, auth: bool = True) -> httpx.Response:
    """Call an MCP tool on the chaos gateway."""
    headers = AUTH_HEADERS if auth else PUBLIC_HEADERS
    return httpx.post(
        f"{GATEWAY_URL}/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": "1",
            "params": {"name": tool_name, "arguments": args},
        },
        headers=headers,
        timeout=30,
    )


def parse_sse_result(resp: httpx.Response) -> dict:
    """Parse SSE response from MCP tool call."""
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            d = json.loads(line[6:])
            content = d.get("result", {}).get("content", [{}])
            if content:
                text = content[0].get("text", "{}")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"raw": text}
    return {}


def stop_container(name: str):
    subprocess.run(["docker", "stop", name], capture_output=True)


def start_container(name: str):
    subprocess.run(["docker", "start", name], capture_output=True)


def toxiproxy_create_proxy(name: str, listen: str, upstream: str):
    """Create a toxiproxy proxy."""
    try:
        httpx.post(f"{TOXIPROXY_API}/proxies", json={
            "name": name, "listen": listen, "upstream": upstream,
        }, timeout=5)
    except Exception:
        pass


def toxiproxy_add_toxic(proxy_name: str, toxic_type: str, attributes: dict):
    """Add a toxic to a proxy (latency, timeout, etc.)."""
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


def wiremock_stub(url_pattern: str, status: int, body: str = "", headers: dict = None, delay_ms: int = 0):
    """Create a wiremock stub."""
    mapping = {
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
