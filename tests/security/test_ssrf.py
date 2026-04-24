"""SSRF tests — marketplace endpoint validation must block internal URLs."""

import pytest

SSRF_URLS = [
    ("http://localhost/admin", "localhost"),
    ("http://127.0.0.1:8080", "loopback_ip"),
    ("http://0.0.0.0:3000", "all_interfaces"),
    ("http://[::1]/internal", "ipv6_loopback"),
    ("http://169.254.169.254/latest/meta-data/", "aws_metadata"),
    ("http://metadata.google.internal/computeMetadata/v1/", "gcp_metadata"),
    ("http://192.168.1.1/admin", "private_classC"),
    ("http://10.0.0.1/internal", "private_classA"),
    ("http://172.16.0.1/private", "private_classB"),
    ("http://internal.local/api", "dot_local"),
    ("http://test.internal/sensitive", "dot_internal"),
]


@pytest.mark.security
@pytest.mark.parametrize("url,label", SSRF_URLS, ids=[s[1] for s in SSRF_URLS])
def test_ssrf_blocked(url, label):
    from src.marketplace import _is_safe_url
    is_safe, reason = _is_safe_url(url)
    assert is_safe is False, f"SSRF not blocked for [{label}] {url}: {reason}"


@pytest.mark.security
def test_safe_url_allowed():
    from src.marketplace import _is_safe_url
    is_safe, _ = _is_safe_url("https://mcp.example.com/mcp")
    assert is_safe is True
