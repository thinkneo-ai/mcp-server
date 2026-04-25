# Tests

## Environment Variables

Tests that call the live gateway require these env vars:

| Variable | Purpose | Where to get |
|----------|---------|-------------|
| `THINKNEO_TEST_API_KEY` | Auth for functional tests against mcp.thinkneo.ai | GitHub secret (set by admin) |
| `ANTHROPIC_API_KEY` | Provider compat tests | Anthropic console |
| `OPENAI_API_KEY` | Provider compat tests | OpenAI dashboard |
| `GOOGLE_API_KEY` | Provider compat tests | Google AI Studio |
| `NVIDIA_API_KEY` | Provider compat tests | build.nvidia.com |

## Running Locally

```bash
# Unit + adversarial + security (no env vars needed)
PYTHONPATH=. pytest tests/unit/ tests/adversarial/ tests/security/ -v

# Functional tests (need THINKNEO_TEST_API_KEY)
export THINKNEO_TEST_API_KEY=your-test-key
PYTHONPATH=. pytest tests/functional/ -v

# Provider compat (need provider keys)
export ANTHROPIC_API_KEY=sk-ant-...
PYTHONPATH=. pytest tests/compat/test_anthropic.py -v
```

## Security Policy

**NEVER put real API keys in test files.** Use `os.environ.get()` with safe fallbacks like `"test-key-not-set"`. See `CONTRIBUTING.md` for details.
