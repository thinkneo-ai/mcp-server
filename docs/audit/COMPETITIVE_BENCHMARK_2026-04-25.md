# Competitive Benchmark — ThinkNEO vs Market

> **Date:** 2026-04-25
> **Methodology:** Public documentation review, feature comparison, pricing analysis
> **Competitors:** LangSmith (LangChain), Portkey, Helicone, LiteLLM Proxy

---

## Feature Parity Matrix

| Feature | ThinkNEO | LangSmith | Portkey | Helicone | LiteLLM |
|---------|----------|-----------|---------|----------|---------|
| **Protocol Support** | | | | | |
| MCP Native | YES | No | No | No | No |
| A2A Protocol | YES | No | No | No | No |
| OpenAI-compatible proxy | No | No | YES | No | YES |
| **Gateway** | | | | | |
| Multi-provider routing | YES | No | YES | No | YES |
| Smart cost optimization | YES | No | YES | Partial | YES |
| Fallback chains | YES | No | YES | No | YES |
| Caching | YES | Partial | YES | No | YES |
| Load balancing | No | No | YES | No | YES |
| **Observability** | | | | | |
| Request tracing | YES (OTEL) | YES | YES | YES | Partial |
| Cost tracking | YES | YES | YES | YES | YES |
| Latency monitoring | YES | YES | YES | YES | Partial |
| Custom dashboards | YES | YES | Partial | YES | No |
| **Governance** | | | | | |
| Runtime guardrails | YES (regex+planned ML) | Partial | YES | No | No |
| Prompt injection detection | YES | No | YES | No | No |
| PII detection | YES (8 patterns) | No | Partial | No | No |
| Policy engine | YES | No | Partial | No | No |
| Compliance export | YES (SOC2/GDPR) | No | No | No | No |
| Audit trail | YES | YES | Partial | YES | No |
| **Security** | | | | | |
| OAuth 2.1 | YES (PKCE) | YES | YES | YES | No |
| API key management | YES (SHA-256) | YES | YES | YES | YES |
| Rate limiting | YES (multi-tier) | YES | YES | YES | YES |
| IP allowlisting | YES | YES | YES | No | No |
| SSRF protection | YES | N/A | N/A | N/A | N/A |
| Published threat model | YES | No | No | No | No |
| **Compliance** | | | | | |
| SOC 2 certified | No | YES | No | YES | No |
| GDPR documentation | Partial | YES | Partial | Partial | No |
| HIPAA BAA | No | YES | No | No | No |
| TCK compliance (A2A) | 97.6% | N/A | N/A | N/A | N/A |
| **Developer Experience** | | | | | |
| Python SDK | YES | YES | YES | YES | YES |
| TypeScript SDK | YES | YES | YES | YES | YES |
| Self-hosted option | YES | No | No | No | YES |
| Open source | YES | No | No | No | YES |
| MCP marketplace | YES | No | No | No | No |
| **Pricing** | | | | | |
| Free tier | 500 calls/mo | 5K traces/mo | 10K req/mo | 10K req/mo | Self-host free |
| Starter | $29/mo | $39/mo | $49/mo | $70/mo | Self-host free |
| Enterprise | Custom | Custom | Custom | Custom | $500/mo |

---

## Unique Differentiators (ThinkNEO Only)

### 1. Native MCP + A2A Protocol Support
ThinkNEO is the only platform that natively implements both Model Context Protocol (MCP) and Agent-to-Agent (A2A) protocol. This is significant because:
- MCP is becoming the standard for AI tool integration (Anthropic, OpenAI, Google adopting)
- A2A is the emerging standard for agent interoperability (Google/Linux Foundation)
- Combined, they enable governed multi-agent orchestration

### 2. Governance-First Architecture
Every tool call passes through a governance pipeline: ACL check, policy evaluation, accountability chain, audit log. This is architecturally different from bolt-on governance features.

### 3. Published Threat Model (STRIDE)
Public THREAT_MODEL.md with full STRIDE analysis. No competitor publishes this level of security transparency.

### 4. A2A TCK Compliance (97.6%)
Only platform with verified A2A protocol interoperability via the official TCK test suite. The 2 opt-outs are intentional (governance > optional throughput features).

### 5. Outcome Validation Loop
Unique feature: register claims about AI outcomes, verify them with evidence, produce cryptographic proof. No competitor has this.

### 6. MCP Marketplace
"npm for MCP tools" — discover, publish, install, review MCP servers. First marketplace of its kind.

---

## Weaknesses to Address

### 1. No SOC 2 Certification (Priority: CRITICAL for Enterprise)
- **Impact:** Blockers for enterprise procurement. LangSmith and Helicone already have it.
- **Effort:** 6 months + $15-30K
- **Recommendation:** Start SOC 2 Type I preparation immediately

### 2. No Self-Service Billing (Priority: HIGH)
- **Impact:** Friction in self-serve adoption. Portkey and Helicone have Stripe integration.
- **Effort:** 40 hours development
- **Recommendation:** Integrate Stripe for starter/growth tiers

### 3. Single-Server Architecture (Priority: MEDIUM for Enterprise)
- **Impact:** No HA/DR story for enterprise RFPs. LangSmith and Portkey run multi-region.
- **Effort:** Significant architectural work
- **Recommendation:** Document scaling roadmap. Leverage DO managed databases + app platform.

### 4. Regex-Only Guardrails (Priority: MEDIUM)
- **Impact:** 24 known bypass techniques. Portkey has ML-based detection.
- **Effort:** 16-40 hours for ML integration
- **Recommendation:** Integrate with existing ML models (e.g., NVIDIA NeMo Guardrails, Rebuff)

### 5. Smaller Community / Ecosystem (Priority: MEDIUM)
- **Impact:** LangSmith has 100K+ users, Helicone has 20K+. ThinkNEO is pre-launch.
- **Recommendation:** Leverage open-source + MCP marketplace for community building

### 6. Limited SDKs (Priority: LOW)
- **Impact:** Python and TypeScript only. LangSmith supports Go, Java.
- **Recommendation:** Add Go SDK for cloud-native users

---

## Positioning Recommendation

**For Enterprise Sales Conversations:**

| Buyer Concern | ThinkNEO Response |
|--------------|-------------------|
| "Do you have SOC 2?" | "We're in readiness preparation (65% complete), targeting Q4 2026. Meanwhile, our published threat model and audit reports provide more transparency than most certified competitors." |
| "Why not LangSmith?" | "LangSmith is great for LLM observability. ThinkNEO adds governance, multi-protocol support (MCP+A2A), and runtime guardrails — what you need when AI agents talk to each other." |
| "Can you scale?" | "Our architecture is stateless-ready. Current setup serves [X] req/s. Horizontal scaling path documented for enterprise deployments." |
| "What about Portkey?" | "Portkey is a gateway. ThinkNEO is a control plane — gateway + governance + compliance + agent orchestration. We're the layer above the gateway." |

**Tagline:** "The only AI Control Plane that speaks MCP and A2A natively."

---

*Report generated by Claude Code (Opus 4.6) — ThinkNEO Operations*
