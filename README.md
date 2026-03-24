# ThinkNEO MCP Server

[![MCP Marketplace](https://img.shields.io/badge/Get%20it%20on-MCP%20Marketplace-blue?style=flat-square)](https://mcp-marketplace.io)

**Enterprise AI Control Plane** — Remote MCP server for ThinkNEO.

Enables Claude, ChatGPT, Copilot, Gemini, and any MCP-compatible client to interact directly with ThinkNEO's governance capabilities: spend tracking, guardrail evaluation, policy enforcement, budget monitoring, compliance status, and provider health.

- **Registry:** `ai.thinkneo/control-plane`
- **Endpoint:** `https://mcp.thinkneo.ai/mcp`
- **Transport:** `streamable-http`
- **Auth:** Bearer token (ThinkNEO API key) for protected tools

---

## Tools

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_check_spend` | AI cost breakdown by provider/model/team | Required |
| `thinkneo_evaluate_guardrail` | Pre-flight prompt safety evaluation | Required |
| `thinkneo_check_policy` | Verify model/provider/action is allowed | Required |
| `thinkneo_get_budget_status` | Budget utilization and enforcement | Required |
| `thinkneo_list_alerts` | Active alerts and incidents | Required |
| `thinkneo_get_compliance_status` | SOC2/GDPR/HIPAA readiness | Required |
| `thinkneo_provider_status` | Real-time AI provider health | **Public** |
| `thinkneo_schedule_demo` | Book a demo with ThinkNEO | **Public** |

---

## Connect in Claude Desktop

Add to `~/.claude/claude_desktop_config.json` (macOS/Linux) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

### With authentication (full access):

```json
{
  "mcpServers": {
    "thinkneo": {
      "url": "https://mcp.thinkneo.ai/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_THINKNEO_API_KEY>"
      }
    }
  }
}
```

### Public tools only (no API key):

```json
{
  "mcpServers": {
    "thinkneo": {
      "url": "https://mcp.thinkneo.ai/mcp"
    }
  }
}
```

To get your ThinkNEO API key, request access at [thinkneo.ai/talk-sales](https://thinkneo.ai/talk-sales) or email [hello@thinkneo.ai](mailto:hello@thinkneo.ai).

---

## Connect in VS Code (GitHub Copilot)

Add to `.vscode/mcp.json` in your workspace or user settings:

```json
{
  "servers": {
    "thinkneo": {
      "type": "http",
      "url": "https://mcp.thinkneo.ai/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_THINKNEO_API_KEY>"
      }
    }
  }
}
```

---

## Test with curl

### List available tools (no auth required):

```bash
curl -X POST https://mcp.thinkneo.ai/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1,
    "params": {}
  }'
```

### Check provider status (public tool):

```bash
curl -X POST https://mcp.thinkneo.ai/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 2,
    "params": {
      "name": "thinkneo_provider_status",
      "arguments": {"provider": "openai"}
    }
  }'
```

### Check AI spend (requires Bearer token):

```bash
curl -X POST https://mcp.thinkneo.ai/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 3,
    "params": {
      "name": "thinkneo_check_spend",
      "arguments": {
        "workspace": "prod-engineering",
        "period": "this-month",
        "group_by": "provider"
      }
    }
  }'
```

### Evaluate a prompt against guardrails (requires Bearer token):

```bash
curl -X POST https://mcp.thinkneo.ai/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <YOUR_API_KEY>" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 4,
    "params": {
      "name": "thinkneo_evaluate_guardrail",
      "arguments": {
        "text": "Summarize this document for me",
        "workspace": "prod-engineering",
        "guardrail_mode": "enforce"
      }
    }
  }'
```

---

## Self-hosted Deployment

### Prerequisites

- Docker + Docker Compose
- Nginx reverse proxy (for HTTPS)

### Quick start

```bash
git clone https://github.com/thinkneo-ai/mcp-server.git
cd mcp-server

# Configure environment
cp .env.example .env
# Edit .env: set THINKNEO_MCP_API_KEYS and THINKNEO_API_KEY

# Build and start
docker compose up -d

# Verify
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1,"params":{}}'
```

### Nginx configuration (HTTPS at mcp.thinkneo.ai)

```nginx
server {
    listen 443 ssl;
    server_name mcp.thinkneo.ai;

    ssl_certificate /etc/letsencrypt/live/mcp.thinkneo.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.thinkneo.ai/privkey.pem;

    location /mcp {
        proxy_pass http://127.0.0.1:8081/mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Required for streamable-http (keep connection open)
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

---

## Publish to MCP Registry

### Option A — DNS authentication (recommended, uses `ai.thinkneo/control-plane` namespace)

```bash
# 1. Generate Ed25519 key pair
openssl genpkey -algorithm Ed25519 -out /tmp/thinkneo-mcp-key.pem

# 2. Get the public key value for the DNS TXT record
PUB=$(openssl pkey -in /tmp/thinkneo-mcp-key.pem -pubout -outform DER | tail -c 32 | base64)
echo "Add DNS TXT record to thinkneo.ai:"
echo "  Host: _mcp"
echo "  Type: TXT"
echo "  Value: v=MCPv1; k=ed25519; p=${PUB}"

# 3. Wait for DNS propagation (usually 5-30 minutes), then publish
mcp-publisher publish \
  --registry-url "https://registry.modelcontextprotocol.io" \
  --mcp-file "./server.json" \
  --auth-method dns \
  --dns-domain thinkneo.ai \
  --dns-private-key /tmp/thinkneo-mcp-key.pem
```

### Option B — GitHub authentication (simpler, uses `io.github.thinkneo-ai/control-plane` namespace)

```bash
mcp-publisher login github
mcp-publisher publish \
  --registry-url "https://registry.modelcontextprotocol.io" \
  --mcp-file "./server.json"
```

### Option C — GitHub Actions (automated on tag push)

See `.github/workflows/publish-mcp.yml` for the full CI/CD workflow.

---

## Verify registry listing

```bash
# Search
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=thinkneo" | jq .

# Direct lookup
curl -s "https://registry.modelcontextprotocol.io/v0/servers/ai.thinkneo%2Fcontrol-plane" | jq .
```

---

## Related

- **ThinkNEO Platform:** [thinkneo.ai](https://thinkneo.ai)
- **A2A Agent:** `https://agent.thinkneo.ai/a2a` (A2A Protocol for agent-to-agent interaction)
- **MCP Registry:** [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io)
- **MCP Spec:** [modelcontextprotocol.io](https://modelcontextprotocol.io)
- **Contact:** [hello@thinkneo.ai](mailto:hello@thinkneo.ai)
