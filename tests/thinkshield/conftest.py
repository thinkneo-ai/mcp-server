"""Shared fixtures for ThinkShield tests."""

from __future__ import annotations

import pytest

from src.thinkshield.config import ShieldSettings
from src.thinkshield.engine import ThinkShieldEngine
from src.thinkshield.types import RequestSnapshot


@pytest.fixture
def engine() -> ThinkShieldEngine:
    return ThinkShieldEngine(ShieldSettings())


@pytest.fixture
def default_settings() -> ShieldSettings:
    return ShieldSettings()


def make_request(
    *,
    method: str = "POST",
    path: str = "/mcp",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    source_ip: str = "203.0.113.1",
    geo_country: str | None = None,
    user_agent: str | None = "MCP-Client/1.0",
    key_hash: str | None = "abc123def456",
    threat_intel=None,
) -> RequestSnapshot:
    """Helper to build a RequestSnapshot with sensible defaults."""
    if headers is None:
        headers = {
            "host": "mcp.thinkneo.ai",
            "content-type": "application/json",
        }
        if user_agent:
            headers["user-agent"] = user_agent
    return RequestSnapshot(
        method=method,
        path=path,
        headers=headers,
        body=body,
        source_ip=source_ip,
        geo_country=geo_country,
        user_agent=user_agent,
        key_hash=key_hash,
        threat_intel=threat_intel,
    )
