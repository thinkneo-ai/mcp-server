# ThinkNEO MCP + A2A Gateway

> Dual-protocol gateway: MCP tools + A2A Protocol agent in a single governed runtime

[![Tests](https://github.com/thinkneo-ai/mcp-server/actions/workflows/tests.yml/badge.svg)](https://github.com/thinkneo-ai/mcp-server/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io)
[![A2A Protocol](https://img.shields.io/badge/A2A-v0.3.0-blue.svg)](https://github.com/google/A2A)
[![Tools](https://img.shields.io/badge/Tools-59-orange.svg)](#mcp-tools)
[![A2A Skills](https://img.shields.io/badge/A2A_Skills-24-blueviolet.svg)](#a2a-capabilities)
[![TCK Compliance](https://img.shields.io/badge/TCK-82%2F82_intentional-brightgreen.svg)](TCK_REPORT.md)
[![Functional](https://img.shields.io/badge/Functional-91%2F91_passing-brightgreen.svg)](FUNCTIONAL_AUDIT.md)
[![Security](https://img.shields.io/badge/Security-0_HIGH-brightgreen.svg)](THREAT_MODEL.md)
[![Free Tier](https://img.shields.io/badge/Free_Tier-500_calls%2Fmo-brightgreen.svg)](#self-signup)
[![Glama](https://glama.ai/mcp/servers/ThinkneoAI/mcp-server/badge)](https://glama.ai/mcp/servers/ThinkneoAI/mcp-server)

---

## Audit this gateway yourself

Run the live audit script from any machine with `curl` and `python3`:

```bash
curl -sSL https://raw.githubusercontent.com/thinkneo-ai/mcp-server/master/scripts/audit_live.sh | bash
```

Tests all surfaces (MCP tools, A2A agent card, security gates, injection/PII detection) in ~20 seconds. Exit code 0 = all OK.

For authenticated tools: `./scripts/audit_live.sh --bearer YOUR_API_KEY`

---

## Status

| Component | Value |
|-----------|-------|
| MCP Protocol | `2024-11-05` (Streamable HTTP) |
| A2A Protocol | `v0.3.0` (Google / Linux Foundation) |
| MCP Tools | 55 |
| A2A Skills | 24 |
| A2A TCK Compliance | **82/82 intentional** (80 passing + 2 documented opt-outs) — [see report](TCK_REPORT.md) |
| Internal Tests | 159/159 passing |
| Production | **Live** at `mcp.thinkneo.ai` |
| Listed on | [Glama.ai](https://glama.ai/mcp/servers/ThinkneoAI/mcp-server) (AAA rating) |

## Live Endpoints

| Endpoint | URL | Method |
|----------|-----|--------|
| MCP (Streamable HTTP) | `https://mcp.thinkneo.ai/mcp` | POST |
| A2A Agent Card | `https://mcp.thinkneo.ai/.well-known/agent.json` | GET |
| A2A Agent | `https://agent.thinkneo.ai/a2a` | POST |
| Health Check | `https://mcp.thinkneo.ai/guardian/health` | GET |
| Developer Docs | `https://mcp.thinkneo.ai/mcp/docs` | GET |
| MCP Marketplace | `https://mcp.thinkneo.ai/registry` | GET |

---

## What This Is

This repository contains the ThinkNEO Gateway, a dual-protocol server that exposes AI governance tools through both the **Model Context Protocol** (MCP, Anthropic 2024) and the **Agent-to-Agent Protocol** (A2A, Google/Linux Foundation 2025).

The gateway implements a bidirectional **MCP-A2A bridge**: MCP clients can dispatch A2A tasks, and A2A agents can call MCP tools. Both protocols share the same governed runtime, meaning all traffic passes through the ThinkNEO Enterprise AI Control Plane for policy enforcement, audit logging, spend tracking, and compliance checks.

The server is production-deployed as a single Docker container, serving MCP on `/mcp` and the A2A Agent Card at `/.well-known/agent.json`. All 55 MCP tools and 24 A2A skills run in the same process, share the same PostgreSQL database, and are wrapped with the same free-tier middleware (500 calls/month, auto-provisioned API keys).

---

## MCP Tools

55 tools across 12 categories. All tools accept JSON-RPC 2.0 via Streamable HTTP.

### Governance (6)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_check_spend` | AI cost breakdown by provider, model, team, and time period | Required |
| `thinkneo_evaluate_guardrail` | Pre-flight prompt safety evaluation against workspace policies | Required |
| `thinkneo_check_policy` | Verify if a model, provider, or action is allowed by governance policies | Required |
| `thinkneo_get_budget_status` | Budget utilization, enforcement status, and projected overage | Required |
| `thinkneo_list_alerts` | Active alerts and incidents for a workspace | Required |
| `thinkneo_get_compliance_status` | SOC2, GDPR, HIPAA compliance readiness and governance score | Required |

### Safety & Detection (Free)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_check` | Prompt safety check: injection patterns (10 rules) + PII (credit card with Luhn, CPF with checksum, SSN, email, phone, API keys) | None |
| `thinkneo_usage` | API key usage stats: calls today/week/month, top tools, estimated cost | None |
| `thinkneo_provider_status` | Real-time health and latency of 7 AI providers | None |
| `thinkneo_read_memory` | Read Claude Code project memory files (index or specific file) | None |
| `thinkneo_write_memory` | Write/update project memory files | Required |
| `thinkneo_schedule_demo` | Book a demo with the ThinkNEO team | None |

### AI Smart Router (3)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_route_model` | Find the cheapest model meeting a quality threshold across 17+ models from 9 providers | Required |
| `thinkneo_get_savings_report` | Cost savings report: original vs actual cost, breakdown by task type | Required |
| `thinkneo_simulate_savings` | Simulate how much an organization would save with Smart Router | None |

### MCP Marketplace (5)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_registry_search` | Search the MCP Marketplace by keyword, category, rating, or verified status | None |
| `thinkneo_registry_get` | Full details for an MCP server package: readme, tools, versions, reviews | None |
| `thinkneo_registry_publish` | Publish an MCP server: validates endpoint, runs security scan, stores entry | Required |
| `thinkneo_registry_review` | Rate and review an MCP server (1-5 stars, one per user per package) | Required |
| `thinkneo_registry_install` | Installation config for Claude Desktop, Cursor, Windsurf, or custom clients | None |

### Trust Score (2)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_evaluate_trust_score` | AI Trust Score (0-100) across 6 dimensions with shareable badge | Required |
| `thinkneo_get_trust_badge` | Public trust score badge lookup by token | None |

### Observability (5)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_start_trace` | Start an observability session for an agent | Required |
| `thinkneo_log_event` | Log a tool call, model call, decision, or error event | Required |
| `thinkneo_end_trace` | End a trace session with final status | Required |
| `thinkneo_get_trace` | Retrieve full trace with all events for a session | Required |
| `thinkneo_get_observability_dashboard` | Aggregated observability metrics for a workspace | Required |

### Value Attribution / ROI (7)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_set_baseline` | Set a pre-AI baseline metric for comparison | Required |
| `thinkneo_log_decision` | Log an AI agent decision with type, rationale, and context | Required |
| `thinkneo_decision_cost` | Calculate the cost of a specific decision | Required |
| `thinkneo_log_risk_avoidance` | Log a risk that was avoided by AI intervention | Required |
| `thinkneo_agent_roi` | ROI report for a specific agent | Required |
| `thinkneo_business_impact` | Business impact report for a workspace | Required |
| `thinkneo_detect_waste` | Detect waste patterns: unused tools, redundant calls, idle agents | Required |

### Outcome Validation (4)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_register_claim` | Register a verifiable claim: what an agent did, with evidence type | Required |
| `thinkneo_verify_claim` | Verify a claim by checking evidence (HTTP status, file exists, DB row, etc.) | Required |
| `thinkneo_get_proof` | Get the full proof chain for a verified claim | Required |
| `thinkneo_verification_dashboard` | Dashboard of all claims, verification rates, and trust metrics | Required |

### Policy Management (4)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_policy_create` | Create a governance policy for a workspace | Required |
| `thinkneo_policy_list` | List all policies for a workspace | Required |
| `thinkneo_policy_evaluate` | Evaluate an action against workspace policies | Required |
| `thinkneo_policy_violations` | List policy violations with severity and remediation | Required |

### Compliance Reporting (2)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_compliance_generate` | Generate a compliance report for a framework | Required |
| `thinkneo_compliance_list` | List available compliance frameworks and their status | Required |

### Benchmarking (3)

| Tool | Description | Auth |
|------|-------------|------|
| `thinkneo_benchmark_compare` | Compare model performance across tasks | Required |
| `thinkneo_benchmark_report` | Generate a benchmark report with recommendations | Required |
| `thinkneo_router_explain` | Explain why the Smart Router chose a specific model | Required |

---

## A2A Capabilities

This gateway is simultaneously an A2A-compliant agent, implementing the [Agent-to-Agent Protocol v0.3.0](https://github.com/google/A2A) maintained by the Linux Foundation.

### Agent Card

Publicly discoverable at [`/.well-known/agent.json`](https://mcp.thinkneo.ai/.well-known/agent.json). Describes all 24 A2A skills, authentication requirements, and runtime capabilities.

[View live Agent Card](https://mcp.thinkneo.ai/.well-known/agent.json)

### MCP-A2A Bridge (4 tools)

Bidirectional protocol translation. An A2A agent can consume MCP tools; an MCP client can dispatch A2A tasks.

| Tool | Description |
|------|-------------|
| `thinkneo_bridge_mcp_to_a2a` | Translate an MCP tool call into an A2A task and dispatch it to an A2A agent |
| `thinkneo_bridge_a2a_to_mcp` | Receive an A2A task, find the matching MCP tool, execute it, return A2A response |
| `thinkneo_bridge_generate_agent_card` | Auto-generate an A2A Agent Card from the MCP tools/list |
| `thinkneo_bridge_list_mappings` | List all current MCP-A2A tool/skill mappings |

### A2A Governance (4 tools)

Full A2A task lifecycle is audited: `task_sent` - `task_accepted` - `task_completed` - flow traced - audit recorded.

| Tool | Description |
|------|-------------|
| `thinkneo_a2a_log` | Log an agent-to-agent interaction with cost, outcome, and latency |
| `thinkneo_a2a_set_policy` | Set communication policies between agents (rate limits, allowed actions) |
| `thinkneo_a2a_flow_map` | Visualize agent-to-agent communication flows over a time period |
| `thinkneo_a2a_audit` | Generate an audit trail of all A2A interactions |

---

## Architecture

```
 MCP Clients                     A2A Agents
 (Claude, Cursor,                (Any A2A-compliant
  ChatGPT, custom)                agent or service)
       |                               |
       |  Streamable HTTP              |  JSON-RPC 2.0
       |  POST /mcp                    |  POST /a2a
       |                               |
       +---------------+---------------+
                       |
              +--------v---------+
              |  ThinkNEO        |
              |  Gateway         |
              |                  |
              |  MCP Runtime     |
              |  A2A Runtime     |
              |  MCP <-> A2A     |
              |  Bridge          |
              +--------+---------+
                       |
           +-----------+-----------+
           |                       |
    +------v-------+       +------v-------+
    | Governance    |       | Data Layer   |
    | Policy Engine |       | PostgreSQL   |
    | FinOps        |       | 33 tables    |
    | Audit Trail   |       | Usage log    |
    | Compliance    |       | API keys     |
    +---------------+       +--------------+
```

---

## TCK Compliance

This gateway implements the A2A Protocol v0.3.0 specification maintained by the Linux Foundation. The official Google-published Technology Compatibility Kit (TCK) validates 82 test cases against the implementation.

**Current status: 80/82 passing + 2 documented opt-outs = 82/82 intentional compliance**

The 2 failing tests are in the `optional_capability` category -- features marked as optional in the specification that are deliberately not implemented. See [TCK_REPORT.md](TCK_REPORT.md) for the detailed breakdown, including the specific test cases that fail and rationale for each.

---

## Quick Start: MCP Client

Add to your Claude Desktop config (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "thinkneo": {
      "url": "https://mcp.thinkneo.ai/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

Or use with Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "thinkneo": {
      "url": "https://mcp.thinkneo.ai/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

## Quick Start: A2A Client

Discover the agent:

```bash
curl https://mcp.thinkneo.ai/.well-known/agent.json
```

Send a task:

```bash
curl -X POST https://agent.thinkneo.ai/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "id": "1",
    "params": {
      "id": "task-001",
      "message": {
        "role": "user",
        "parts": [{"text": "Check if this prompt is safe: ignore all previous instructions"}]
      }
    }
  }'
```

---

## Rate Limits

Multi-dimensional rate limiting per API key with standard HTTP headers.

| Tier | Burst/second | Per minute | Monthly |
|------|-------------|------------|---------|
| Free | 10 | 60 | 500 |
| Starter/Pro | 100 | 600 | 5,000 |
| Enterprise | 1,000 | 6,000 | Unlimited |

Every response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. Exceeded limits return `429` with `Retry-After`. See [docs/features/rate-limiting.md](docs/features/rate-limiting.md).

---

## Observability Integrations

Native OpenTelemetry support — traces and metrics for every MCP tool call and A2A skill invocation.

Enable with environment variables (disabled by default, zero overhead when off):

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=thinkneo-mcp-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4317
```

**Metrics exported:**
- `thinkneo.tool_calls_total` — Counter per tool + status (ok/error)
- `thinkneo.tool_duration_seconds` — Histogram per tool
- `thinkneo.active_requests` — Gauge of concurrent requests

**Vendor guides:**
- [Datadog](docs/integrations/datadog.md)
- [Grafana Tempo + Prometheus](docs/integrations/grafana-tempo.md)
- [Honeycomb](docs/integrations/honeycomb.md)

---

## Authentication

- **API Key**: Prefix `tnk_`, provided via `Authorization: Bearer <key>` header
- **OAuth 2.1**: Full authorization code flow supported
- Public tools (safety checks, provider status, marketplace search) work without authentication

## Self-Signup

Auto-provision a free API key (500 calls/month):

```
POST https://mcp.thinkneo.ai/mcp/signup
```

No credit card required. All 55 tools available on the free tier.

## Self-Hosted Deployment

Run ThinkNEO gateway on your own infrastructure:

```bash
git clone https://github.com/thinkneo-ai/mcp-server.git
cd mcp-server/deploy
cp .env.example .env    # edit with your API key
docker compose up -d    # gateway + PostgreSQL
```

Gateway at `http://localhost:8081/mcp`. See [self-hosted quickstart](docs/self-hosted/quickstart.md).

---

## Enterprise Features

- Per-minute rate limiting with configurable thresholds
- IP allowlist per API key
- Granular scopes (`read`, `execute`, custom)
- API key rotation with revocation log
- Enterprise tier with unlimited calls
- OAuth 2.1 with client credentials flow
- Dedicated support and SLA

Contact: [hello@thinkneo.ai](mailto:hello@thinkneo.ai)

---

## License

[MIT](LICENSE)

## Links

- **Website**: [thinkneo.ai](https://thinkneo.ai)
- **Developer Docs**: [mcp.thinkneo.ai/mcp/docs](https://mcp.thinkneo.ai/mcp/docs)
- **MCP Marketplace**: [mcp.thinkneo.ai/registry](https://mcp.thinkneo.ai/registry)
- **Glama Listing**: [glama.ai/mcp/servers/ThinkneoAI/mcp-server](https://glama.ai/mcp/servers/ThinkneoAI/mcp-server)
- **A2A Agent Card**: [mcp.thinkneo.ai/.well-known/agent.json](https://mcp.thinkneo.ai/.well-known/agent.json)
- **Company**: ThinkNEO AI Technology Co. Ltd (Hong Kong) | NVIDIA Inception Member | Anthropic Partner Network
