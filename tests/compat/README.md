# Provider Compatibility Tests

Daily tests against live provider APIs to detect regressions before customers do.

## Model IDs (last verified: 2026-04-25)

| Provider | Model ID | Tests |
|----------|----------|-------|
| Anthropic | `claude-sonnet-4-20250514` | chat, streaming, tool_use, usage |
| Anthropic | `claude-haiku-4-5-20251001` | chat, streaming, usage |
| Anthropic | `claude-opus-4-20250414` | chat (1 call, expensive) |
| OpenAI | `gpt-4o` | chat, usage |
| OpenAI | `gpt-4o-mini` | chat, streaming, tool_use, usage |
| OpenAI | `gpt-4.1` | chat |
| Google | `gemini-2.5-flash` | chat, streaming, usage |
| Google | `gemini-2.5-pro` | chat |
| NVIDIA | `nvidia/llama-3.1-nemotron-70b-instruct` | chat, usage |
| NVIDIA | `nvidia/nemotron-mini-4b-instruct` | chat |

## Updating Model IDs

When a provider deprecates a model:

1. Check the provider's docs for the replacement model ID
2. Update the `MODELS` list in the corresponding test file
3. Update this README with the new ID and verification date
4. Commit: `chore(compat): update <provider> model IDs`

## Running Locally

```bash
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
export GOOGLE_API_KEY=AI...
export NVIDIA_API_KEY=nvapi-...

pytest tests/compat/ -v --timeout=60
```

## Schedule

Daily at 09:00 UTC via GitHub Actions (`provider_compat.yml`).
Manual trigger: `gh workflow run provider_compat.yml`
