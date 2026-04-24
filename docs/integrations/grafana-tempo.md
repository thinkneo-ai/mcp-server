# Grafana Tempo + Prometheus Integration

Send ThinkNEO MCP gateway traces to Grafana Tempo and metrics to Prometheus.

## Architecture

```
ThinkNEO Gateway → OTEL Collector → Tempo (traces)
                                   → Prometheus (metrics)
                                   → Grafana (dashboards)
```

## 1. Deploy OTEL Collector

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true
  prometheus:
    endpoint: 0.0.0.0:8889

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
```

## 2. Configure ThinkNEO Gateway

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=thinkneo-mcp-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

## 3. Docker Compose (all-in-one)

```yaml
services:
  thinkneo-mcp:
    image: thinkneo-mcp-server:latest
    environment:
      OTEL_ENABLED: "true"
      OTEL_SERVICE_NAME: "thinkneo-mcp-gateway"
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml
    ports:
      - "4317:4317"
      - "8889:8889"

  tempo:
    image: grafana/tempo:latest
    ports:
      - "3200:3200"

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
```

## 4. Grafana Data Sources

- **Tempo**: `http://tempo:3200`
- **Prometheus**: `http://prometheus:9090` (scrape `otel-collector:8889`)

## 5. Verify

1. Open Grafana at `http://localhost:3000`
2. Go to Explore > Tempo > Search for `service.name = thinkneo-mcp-gateway`
3. See traces with `POST /mcp` → `tool.<name>` child spans
4. In Prometheus, query `thinkneo_tool_calls_total` or `thinkneo_tool_duration_seconds_bucket`
