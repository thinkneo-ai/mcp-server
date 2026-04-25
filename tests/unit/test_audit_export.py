"""
Unit tests for SIEM audit export — formatters, engine, HMAC, integrations.
"""

import csv
import hmac
import hashlib
import io
import json
import time
import pytest
from unittest.mock import patch, MagicMock

from src.audit.formatters.json_fmt import format_json
from src.audit.formatters.cef import format_cef, _escape_header, _escape_ext
from src.audit.formatters.leef import format_leef
from src.audit.formatters.syslog_fmt import format_syslog
from src.audit.formatters.csv_fmt import format_csv
from src.audit.export import export_events

SAMPLE_EVENTS = [
    {"event_type": "tool_call", "tool_name": "thinkneo_check", "timestamp": "2026-04-25T10:00:00Z",
     "cost_usd": 0.002, "latency_ms": 45, "key_prefix": "tnk_8753", "workspace": "prod"},
    {"event_type": "task_sent", "from_agent": "agent-a", "to_agent": "agent-b",
     "timestamp": "2026-04-25T10:01:00Z", "cost_usd": 0.01, "outcome": "success"},
]


# ── Formatter Tests ─────────────────────────────────────────

class TestJSONFormatter:
    def test_valid_json_lines(self):
        result = format_json(SAMPLE_EVENTS)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)

    def test_empty_events(self):
        assert format_json([]) == ""


class TestCEFFormatter:
    def test_cef_structure(self):
        result = format_cef(SAMPLE_EVENTS)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert line.startswith("CEF:0|ThinkNEO|MCP Gateway|")
            parts = line.split("|")
            assert len(parts) >= 7

    def test_cef_escape_pipe(self):
        assert _escape_header("test|value") == "test\\|value"

    def test_cef_escape_equals(self):
        assert _escape_ext("key=val") == "key\\=val"

    def test_cef_escape_backslash(self):
        assert _escape_header("test\\value") == "test\\\\value"

    def test_cef_severity_error(self):
        events = [{"event_type": "error", "timestamp": "2026-04-25T10:00:00Z"}]
        result = format_cef(events)
        assert "|7|" in result  # severity 7 for errors


class TestLEEFFormatter:
    def test_leef_structure(self):
        result = format_leef(SAMPLE_EVENTS)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert line.startswith("LEEF:2.0|ThinkNEO|MCP Gateway|")

    def test_leef_tab_separated_extensions(self):
        result = format_leef(SAMPLE_EVENTS)
        line = result.strip().split("\n")[0]
        # After the 5th pipe, extensions are tab-separated
        ext_part = line.split("|", 5)[-1]
        assert "\t" in ext_part


class TestSyslogFormatter:
    def test_syslog_structure(self):
        result = format_syslog(SAMPLE_EVENTS)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            assert line.startswith("<")
            assert "mcp.thinkneo.ai" in line
            assert "thinkneo-gateway" in line

    def test_syslog_timestamp_utc(self):
        result = format_syslog(SAMPLE_EVENTS)
        line = result.strip().split("\n")[0]
        # Timestamp should end with Z (UTC)
        parts = line.split(" ")
        ts = parts[1]  # timestamp is second field after PRI
        assert ts.endswith("Z"), f"Timestamp not UTC: {ts}"

    def test_syslog_structured_data(self):
        result = format_syslog(SAMPLE_EVENTS)
        assert "[thinkneo" in result
        assert 'tool_name="thinkneo_check"' in result

    def test_syslog_error_severity(self):
        events = [{"event_type": "error", "timestamp": "2026-04-25T10:00:00Z"}]
        result = format_syslog(events)
        assert "<132>" in result  # PRI for warning (local0.warning)


class TestCSVFormatter:
    def test_csv_header_and_rows(self):
        result = format_csv(SAMPLE_EVENTS)
        reader = csv.reader(io.StringIO(result))
        rows = list(reader)
        assert rows[0][0] == "timestamp"  # header
        assert len(rows) == 3  # header + 2 events

    def test_csv_empty(self):
        result = format_csv([])
        lines = result.strip().split("\n")
        assert len(lines) == 1  # header only


# ── Export Engine Tests ──────────────────────────────────────

class TestExportEngine:
    def test_export_json(self):
        result = export_events(SAMPLE_EVENTS, "json")
        assert result["format"] == "json"
        assert result["event_count"] == 2
        assert "data" in result

    def test_export_unknown_format(self):
        result = export_events(SAMPLE_EVENTS, "xml")
        assert "error" in result

    def test_export_empty(self):
        result = export_events([], "json")
        assert result["event_count"] == 0


# ── HMAC Signing Tests ───────────────────────────────────────

class TestHMACSigning:
    def test_hmac_signature_present(self):
        result = export_events(SAMPLE_EVENTS, "json", sign_hmac=True, hmac_key="secret123")
        assert "hmac_sha256" in result
        assert result["hmac_algorithm"] == "HMAC-SHA256"

    def test_hmac_signature_consistent(self):
        r1 = export_events(SAMPLE_EVENTS, "json", sign_hmac=True, hmac_key="key1")
        r2 = export_events(SAMPLE_EVENTS, "json", sign_hmac=True, hmac_key="key1")
        assert r1["hmac_sha256"] == r2["hmac_sha256"]

    def test_hmac_different_keys(self):
        r1 = export_events(SAMPLE_EVENTS, "json", sign_hmac=True, hmac_key="key1")
        r2 = export_events(SAMPLE_EVENTS, "json", sign_hmac=True, hmac_key="key2")
        assert r1["hmac_sha256"] != r2["hmac_sha256"]

    def test_hmac_verifiable(self):
        key = "verify-me"
        result = export_events(SAMPLE_EVENTS, "json", sign_hmac=True, hmac_key=key)
        expected = hmac.new(key.encode(), result["data"].encode(), hashlib.sha256).hexdigest()
        assert result["hmac_sha256"] == expected

    def test_no_hmac_when_disabled(self):
        result = export_events(SAMPLE_EVENTS, "json", sign_hmac=False)
        assert "hmac_sha256" not in result


# ── Integration Mock Tests ───────────────────────────────────

class TestSplunkIntegration:
    def test_splunk_push_success(self):
        from src.audit.integrations.splunk import push_to_splunk
        with patch("src.audit.integrations.splunk.httpx.post") as mock:
            mock.return_value = MagicMock(status_code=200)
            result = push_to_splunk("https://splunk.test:8088/services/collector", "token", SAMPLE_EVENTS)
        assert result["status"] == "success"
        assert result["events_sent"] > 0

    def test_splunk_retry_on_500(self):
        from src.audit.integrations.splunk import push_to_splunk
        with patch("src.audit.integrations.splunk.httpx.post") as mock:
            mock.side_effect = [MagicMock(status_code=500, text="error"), MagicMock(status_code=200)]
            with patch("src.audit.integrations.splunk.time.sleep"):
                result = push_to_splunk("https://splunk.test:8088/services/collector", "tok", SAMPLE_EVENTS)
        assert result["status"] == "success"


class TestElasticIntegration:
    def test_elastic_push_success(self):
        from src.audit.integrations.elastic import push_to_elastic
        with patch("src.audit.integrations.elastic.httpx.post") as mock:
            mock.return_value = MagicMock(status_code=200, json=lambda: {"errors": False, "items": []})
            result = push_to_elastic("https://elastic.test:9200", "apikey", SAMPLE_EVENTS)
        assert result["status"] == "success"


class TestWebhookIntegration:
    def test_webhook_push_success(self):
        from src.audit.integrations.webhook import push_to_webhook
        with patch("src.audit.integrations.webhook.httpx.post") as mock:
            mock.return_value = MagicMock(status_code=200)
            result = push_to_webhook("https://webhook.test/ingest", events=SAMPLE_EVENTS)
        assert result["status"] == "success"
        assert result["events_sent"] == 2
