"""
OpenTelemetry ASGI Middleware for ThinkNEO Gateway.

Creates root spans for HTTP requests with method, path, status code.
Propagates trace context from incoming headers (W3C Trace Context).
Records active_requests gauge.
"""

from __future__ import annotations

import time
from starlette.types import ASGIApp, Receive, Scope, Send

from ..otel import is_otel_enabled, get_tracer, active_requests


class OTELMiddleware:
    """
    Pure ASGI middleware — follows the same pattern as BearerTokenMiddleware.
    Must preserve FastMCP lifespan propagation (no Mount wrapping).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_otel_enabled():
            await self.app(scope, receive, send)
            return

        tracer = get_tracer()
        if tracer is None:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")

        # Extract trace context from incoming headers (W3C Trace Context)
        headers = dict(scope.get("headers", []))
        traceparent = headers.get(b"traceparent", b"").decode("utf-8", errors="ignore")

        # Create parent context from traceparent if present
        context = None
        if traceparent:
            try:
                from opentelemetry.propagators.textmap import DefaultTextMapPropagator
                from opentelemetry.context import Context
                propagator = DefaultTextMapPropagator()
                carrier = {"traceparent": traceparent}
                tracestate = headers.get(b"tracestate", b"").decode("utf-8", errors="ignore")
                if tracestate:
                    carrier["tracestate"] = tracestate
                context = propagator.extract(carrier)
            except Exception:
                pass

        # Track response status
        response_status = [200]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_status[0] = message.get("status", 200)
            await send(message)

        # Create span
        with tracer.start_as_current_span(
            f"{method} {path}",
            context=context,
            attributes={
                "http.method": method,
                "http.target": path,
                "http.scheme": scope.get("scheme", "https"),
            },
        ) as span:
            if active_requests:
                active_requests.add(1)

            start = time.perf_counter()
            try:
                await self.app(scope, receive, send_wrapper)
                span.set_attribute("http.status_code", response_status[0])
            except Exception as exc:
                span.set_attribute("http.status_code", 500)
                span.record_exception(exc)
                raise
            finally:
                if active_requests:
                    active_requests.add(-1)
                duration = time.perf_counter() - start
                span.set_attribute("http.duration_ms", round(duration * 1000, 1))
