# Honeycomb Integration

Send ThinkNEO MCP gateway traces and metrics directly to Honeycomb via OTLP.

## Prerequisites

- Honeycomb account (free tier: 20M events/month)
- API key from Honeycomb Settings > API Keys

## Configuration

Honeycomb accepts OTLP natively — no collector needed.

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=thinkneo-mcp-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_HEADERS=x-honeycomb-team=<YOUR_HONEYCOMB_API_KEY>
```

## Docker Compose

```yaml
services:
  thinkneo-mcp:
    image: thinkneo-mcp-server:latest
    environment:
      OTEL_ENABLED: "true"
      OTEL_SERVICE_NAME: "thinkneo-mcp-gateway"
      OTEL_EXPORTER_OTLP_ENDPOINT: "https://api.honeycomb.io"
      OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf"
      OTEL_EXPORTER_OTLP_HEADERS: "x-honeycomb-team=${HONEYCOMB_API_KEY}"
```

## Verify

1. Open Honeycomb > your environment
2. Query: `WHERE service.name = "thinkneo-mcp-gateway"`
3. See traces with:
   - `http.method`, `http.target`, `http.status_code` on root spans
   - `thinkneo.tool_name`, `thinkneo.tool_status` on child spans
4. Create Board with:
   - `HEATMAP(duration_ms) GROUP BY thinkneo.tool_name` — latency per tool
   - `COUNT GROUP BY thinkneo.tool_status` — success/error ratio

## Metrics

Honeycomb converts OTEL metrics to queryable columns:

| Metric | Honeycomb Column | Query Example |
|--------|-----------------|---------------|
| `thinkneo.tool_calls_total` | `thinkneo.tool_calls_total` | `SUM(thinkneo.tool_calls_total) GROUP BY tool` |
| `thinkneo.tool_duration_seconds` | `thinkneo.tool_duration_seconds` | `P99(thinkneo.tool_duration_seconds) GROUP BY tool` |
| `thinkneo.active_requests` | `thinkneo.active_requests` | `MAX(thinkneo.active_requests)` |
