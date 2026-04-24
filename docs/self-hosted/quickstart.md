# Self-Hosted Quickstart

Deploy ThinkNEO MCP+A2A Gateway on your own infrastructure in under 5 minutes.

## Prerequisites

- Docker 24+ and Docker Compose v2
- 1 CPU core, 512MB RAM minimum
- Port 8081 available

## 1. Clone and configure

```bash
git clone https://github.com/thinkneo-ai/mcp-server.git
cd mcp-server/deploy
cp .env.example .env
```

Edit `.env` to set your API key:
```bash
THINKNEO_API_KEY=your-secret-api-key-here
MCP_DB_PASSWORD=your-secure-db-password
```

## 2. Start

```bash
docker compose up -d
```

This starts:
- **thinkneo-gateway** on port 8081 (MCP + A2A)
- **thinkneo-postgres** on port 5432 (internal, not exposed)

## 3. Verify

```bash
# Health check
curl http://localhost:8081/guardian/health

# MCP Initialize
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# Call a tool
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-api-key-here" \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":2,"params":{"name":"thinkneo_check","arguments":{"text":"Hello world"}}}'
```

## 4. Connect Claude Desktop

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "thinkneo": {
      "url": "http://localhost:8081/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-api-key-here"
      }
    }
  }
}
```

## 5. Observability (optional)

Enable OpenTelemetry by setting in `.env`:

```bash
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4317
```

See [OpenTelemetry docs](../integrations/) for vendor-specific setup.

## Updating

```bash
cd mcp-server
git pull
cd deploy
docker compose build
docker compose up -d
```

## Data Persistence

- PostgreSQL data: `postgres_data` Docker volume
- Memory files: `memory_data` Docker volume

To backup: `docker run --rm -v postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/pg_backup.tar.gz /data`
