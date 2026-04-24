"""
OpenTelemetry setup for ThinkNEO MCP+A2A Gateway.

Provides traces, metrics, and structured spans for all MCP tools and A2A skills.
Disabled by default — enable with OTEL_ENABLED=true.

Environment variables (standard OTEL spec):
    OTEL_ENABLED=true                              # opt-in
    OTEL_SERVICE_NAME=thinkneo-mcp-gateway         # service name
    OTEL_EXPORTER_OTLP_ENDPOINT=http://host:4317   # gRPC endpoint
    OTEL_EXPORTER_OTLP_PROTOCOL=grpc               # grpc or http/protobuf
    OTEL_TRACES_SAMPLER=parentbased_traceid_ratio   # sampling strategy
    OTEL_TRACES_SAMPLER_ARG=1.0                     # sample ratio (0.0-1.0)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_otel_enabled: bool = False
_tracer = None
_meter = None

# Metrics instruments (initialized in setup_otel)
tool_calls_total = None       # Counter: total calls per tool+status
tool_duration_seconds = None  # Histogram: latency per tool
active_requests = None        # UpDownCounter: concurrent requests


def is_otel_enabled() -> bool:
    return _otel_enabled


def get_tracer():
    return _tracer


def get_meter():
    return _meter


def setup_otel() -> None:
    """Initialize OpenTelemetry if OTEL_ENABLED=true."""
    global _otel_enabled, _tracer, _meter
    global tool_calls_total, tool_duration_seconds, active_requests

    if os.getenv("OTEL_ENABLED", "").lower() not in ("true", "1", "yes"):
        logger.info("OTEL disabled (set OTEL_ENABLED=true to enable)")
        return

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource

        protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        service_name = os.getenv("OTEL_SERVICE_NAME", "thinkneo-mcp-gateway")

        resource = Resource.create({"service.name": service_name})

        # --- Traces ---
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            trace_exporter = OTLPSpanExporter(endpoint=endpoint + "/v1/traces")
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            trace_exporter = OTLPSpanExporter(endpoint=endpoint)

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer("thinkneo.gateway", "3.2.0")

        # --- Metrics ---
        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            metric_exporter = OTLPMetricExporter(endpoint=endpoint + "/v1/metrics")
        else:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            metric_exporter = OTLPMetricExporter(endpoint=endpoint)

        metric_reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=30000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter("thinkneo.gateway", "3.2.0")

        # Create metric instruments
        tool_calls_total = _meter.create_counter(
            "thinkneo.tool_calls_total",
            description="Total MCP tool calls",
            unit="1",
        )
        tool_duration_seconds = _meter.create_histogram(
            "thinkneo.tool_duration_seconds",
            description="Tool call duration in seconds",
            unit="s",
        )
        active_requests = _meter.create_up_down_counter(
            "thinkneo.active_requests",
            description="Number of active requests being processed",
            unit="1",
        )

        _otel_enabled = True
        logger.info(
            "OTEL enabled: service=%s endpoint=%s protocol=%s",
            service_name, endpoint, protocol,
        )

    except ImportError as e:
        logger.warning("OTEL packages not installed: %s", e)
    except Exception as e:
        logger.error("OTEL setup failed: %s", e)
