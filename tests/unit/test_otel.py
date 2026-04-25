"""
Unit tests for OpenTelemetry integration.

Tests setup, middleware, tool wrapping, metrics, sampling, and context propagation.
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock


class TestOTELSetup:
    def test_otel_disabled_by_default(self):
        """OTEL should be disabled when OTEL_ENABLED is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to reset state
            import importlib
            import src.otel
            importlib.reload(src.otel)
            assert src.otel.is_otel_enabled() is False

    def test_otel_enabled_when_env_set(self):
        """OTEL should enable when OTEL_ENABLED=true."""
        with patch.dict(os.environ, {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "OTEL_SERVICE_NAME": "test-service",
        }):
            import importlib
            import src.otel
            importlib.reload(src.otel)
            src.otel.setup_otel()
            assert src.otel.is_otel_enabled() is True
            assert src.otel.get_tracer() is not None
            assert src.otel.get_meter() is not None
            # Cleanup
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel._meter = None

    def test_otel_creates_metrics_instruments(self):
        """setup_otel should create counter, histogram, and gauge."""
        with patch.dict(os.environ, {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }):
            import importlib
            import src.otel
            importlib.reload(src.otel)
            src.otel.setup_otel()
            assert src.otel.tool_calls_total is not None
            assert src.otel.tool_duration_seconds is not None
            assert src.otel.active_requests is not None
            # Cleanup
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel._meter = None

    def test_otel_http_protocol(self):
        """OTEL should work with http/protobuf protocol."""
        with patch.dict(os.environ, {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        }):
            import importlib
            import src.otel
            importlib.reload(src.otel)
            src.otel.setup_otel()
            assert src.otel.is_otel_enabled() is True
            # Cleanup
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel._meter = None

    def test_otel_grpc_protocol(self):
        """OTEL should work with gRPC protocol (default)."""
        with patch.dict(os.environ, {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        }):
            import importlib
            import src.otel
            importlib.reload(src.otel)
            src.otel.setup_otel()
            assert src.otel.is_otel_enabled() is True
            # Cleanup
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel._meter = None


class TestOTELMiddleware:
    def test_passes_through_non_http(self):
        """Non-HTTP scopes should pass through without instrumentation."""
        import asyncio
        from src.middleware.otel_middleware import OTELMiddleware

        called = []

        async def mock_app(scope, receive, send):
            called.append(True)

        middleware = OTELMiddleware(mock_app)

        async def run():
            scope = {"type": "lifespan"}
            await middleware(scope, MagicMock(), MagicMock())
            assert len(called) == 1

        asyncio.run(run())

    def test_passes_through_when_otel_disabled(self):
        """HTTP requests should pass through without spans when OTEL disabled."""
        import asyncio
        from src.middleware.otel_middleware import OTELMiddleware

        called = []

        async def mock_app(scope, receive, send):
            called.append(True)

        middleware = OTELMiddleware(mock_app)

        async def run():
            scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": []}
            with patch("src.otel._otel_enabled", False):
                await middleware(scope, MagicMock(), MagicMock())
            assert len(called) == 1

        asyncio.run(run())


class TestToolWrapperOTEL:
    def test_tool_works_without_otel(self, all_tools, mock_db):
        """Tools should work normally when OTEL is disabled."""
        from tests.conftest import tool_fn, parse_tool_result
        with patch("src.otel._otel_enabled", False):
            fn = tool_fn(all_tools, "thinkneo_check")
            result = parse_tool_result(fn(text="hello"))
            assert result["safe"] is True

    def test_tool_works_with_otel_enabled(self, all_tools, mock_db):
        """Tools should work when OTEL is enabled (spans created)."""
        from tests.conftest import tool_fn, parse_tool_result

        # Setup minimal OTEL
        with patch.dict(os.environ, {
            "OTEL_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        }):
            import src.otel
            src.otel.setup_otel()

            fn = tool_fn(all_tools, "thinkneo_check")
            result = parse_tool_result(fn(text="hello"))
            assert result["safe"] is True

            # Cleanup
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel._meter = None

    def test_no_pii_in_span_attributes(self, all_tools, mock_db):
        """Tool arguments should NOT be recorded in spans (PII risk).
        Verified by checking the span mock — only tool_name and tool_status are set."""
        from tests.conftest import tool_fn
        import src.otel

        span_mock = MagicMock()
        tracer_mock = MagicMock()
        tracer_mock.start_as_current_span.return_value.__enter__ = MagicMock(return_value=span_mock)
        tracer_mock.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        src.otel._otel_enabled = True
        src.otel._tracer = tracer_mock
        src.otel.tool_calls_total = MagicMock()
        src.otel.tool_duration_seconds = MagicMock()

        try:
            fn = tool_fn(all_tools, "thinkneo_check")
            fn(text="My SSN is 123-45-6789")

            # Check all set_attribute calls — PII text must NOT appear
            for call in span_mock.set_attribute.call_args_list:
                key, value = call[0]
                if isinstance(value, str):
                    assert "123-45-6789" not in value, f"PII found in span attribute {key}={value}"
                    assert "My SSN" not in value, f"PII found in span attribute {key}={value}"
        finally:
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel.tool_calls_total = None
            src.otel.tool_duration_seconds = None

    def test_span_has_tool_name(self, all_tools, mock_db):
        """Tool spans should have thinkneo.tool_name attribute."""
        from tests.conftest import tool_fn
        import src.otel

        span_mock = MagicMock()
        tracer_mock = MagicMock()
        tracer_mock.start_as_current_span.return_value.__enter__ = MagicMock(return_value=span_mock)
        tracer_mock.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

        src.otel._otel_enabled = True
        src.otel._tracer = tracer_mock
        src.otel.tool_calls_total = MagicMock()
        src.otel.tool_duration_seconds = MagicMock()

        try:
            fn = tool_fn(all_tools, "thinkneo_check")
            fn(text="hello")

            # Verify span was created with tool name
            tracer_mock.start_as_current_span.assert_called_with("tool.thinkneo_check")

            # Verify attributes were set
            attr_calls = {call[0][0]: call[0][1] for call in span_mock.set_attribute.call_args_list}
            assert attr_calls.get("thinkneo.tool_name") == "thinkneo_check"
            assert attr_calls.get("thinkneo.tool_status") == "ok"
        finally:
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel.tool_calls_total = None
            src.otel.tool_duration_seconds = None

    def test_metrics_counter_incremented(self, all_tools, mock_db):
        """tool_calls_total counter should be incremented on tool call."""
        from tests.conftest import tool_fn
        import src.otel

        mock_counter = MagicMock()
        mock_histogram = MagicMock()

        src.otel._otel_enabled = True
        src.otel._tracer = MagicMock()
        src.otel._tracer.start_as_current_span = MagicMock()
        # Make the context manager work
        span_mock = MagicMock()
        src.otel._tracer.start_as_current_span.return_value.__enter__ = MagicMock(return_value=span_mock)
        src.otel._tracer.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)
        src.otel.tool_calls_total = mock_counter
        src.otel.tool_duration_seconds = mock_histogram

        try:
            fn = tool_fn(all_tools, "thinkneo_check")
            fn(text="hello")
            mock_counter.add.assert_called()
            mock_histogram.record.assert_called()
        finally:
            src.otel._otel_enabled = False
            src.otel._tracer = None
            src.otel.tool_calls_total = None
            src.otel.tool_duration_seconds = None
