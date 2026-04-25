# Sub-Processor List

> **Controller:** ThinkNEO AI Technology Co., Limited (Hong Kong)
> **Last updated:** 2026-04-25
> **Review cadence:** Quarterly or upon material change

ThinkNEO engages the following sub-processors to deliver the ThinkNEO MCP+A2A Gateway service. Customers will be notified at least 30 days before any material change to this list.

---

## Infrastructure Sub-Processors

These sub-processors host or operate components of the ThinkNEO service.

| Sub-Processor | Purpose | Data Processed | Location | DPA Status |
|---------------|---------|----------------|----------|------------|
| **DigitalOcean, LLC** | Cloud hosting (compute, storage, networking) | API key hashes, usage logs, memory files, configuration | NYC1, US | [DigitalOcean DPA](https://www.digitalocean.com/legal/data-processing-agreement) |
| **Resend, Inc.** | Transactional email delivery (welcome emails, alerts) | Email addresses, email content | US | [Resend DPA](https://resend.com/legal/dpa) |
| **Let's Encrypt (ISRG)** | TLS certificate issuance and renewal | Domain names only (no customer data) | US | N/A (public CA, no personal data) |

## Customer-Directed Providers

These providers are invoked **only when the customer explicitly directs ThinkNEO to do so** (e.g., via Smart Router model selection). ThinkNEO acts as a pass-through; these are not sub-processors under GDPR Article 28 because ThinkNEO does not determine the purposes of processing.

| Provider | When Used | Data Flow |
|----------|-----------|-----------|
| **Anthropic, PBC** | When customer routes requests to Claude models | Prompt/response pass-through via API |
| **OpenAI, Inc.** | When customer routes requests to GPT models | Prompt/response pass-through via API |
| **Google LLC** | When customer routes requests to Gemini models | Prompt/response pass-through via API |
| **NVIDIA Corporation** | When customer uses NVIDIA NIM/NeMo endpoints | Prompt/response pass-through via API |
| **Tencent Cloud** | When customer uses Hunyuan models (e.g., 3D generation) | Prompt/response pass-through via API |

## Not Currently Active

These processors are planned but not yet active:

| Processor | Purpose | Status |
|-----------|---------|--------|
| **Stripe, Inc.** | Payment processing for paid tiers | Planned Q3 2026 |
| **AWS (Amazon)** | Offsite backup storage | Planned Q3 2026 |

---

## Changes

| Date | Change |
|------|--------|
| 2026-04-25 | Initial publication |

---

## Contact

For questions about sub-processors or to request notification of changes:
- **Email:** privacy@thinkneo.ai
- **DPO contact:** dpo@thinkneo.ai

---

*ThinkNEO AI Technology Co., Limited*
