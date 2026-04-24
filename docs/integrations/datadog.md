# Datadog Integration

Send ThinkNEO MCP gateway traces and metrics to Datadog via OTLP.

## Prerequisites

- Datadog Agent v7.32+ with OTLP ingest enabled
- OR Datadog API key for direct OTLP export

## Option 1: Via Datadog Agent (recommended)

The Datadog Agent receives OTLP data locally and forwards to Datadog.

### 1. Configure Datadog Agent

Add to your `datadog.yaml`:

```yaml
otlp_config:
  receiver:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
```

### 2. Configure ThinkNEO Gateway

```bash
# docker-compose.yml environment:
OTEL_ENABLED=true
OTEL_SERVICE_NAME=thinkneo-mcp-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://datadog-agent:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

### 3. Verify

In Datadog APM > Traces, search for `service:thinkneo-mcp-gateway`.

You should see:
- `POST /mcp` root spans with HTTP status, latency
- `tool.<name>` child spans for each MCP tool call
- Metrics: `thinkneo.tool_calls_total`, `thinkneo.tool_duration_seconds`

## Option 2: Direct OTLP Export (no Agent)

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=thinkneo-mcp-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=https://trace.agent.datadoghq.com
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_HEADERS=DD-API-KEY=<your-datadog-api-key>
```

## Metrics Available

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `thinkneo.tool_calls_total` | Counter | tool, status | Total tool calls |
| `thinkneo.tool_duration_seconds` | Histogram | tool | Call duration |
| `thinkneo.active_requests` | Gauge | — | Concurrent requests |

## Dashboards

Import the sample dashboard from `docs/integrations/datadog-dashboard.json` (coming soon).
