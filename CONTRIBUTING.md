# Contributing to ThinkNEO MCP Server

## Setup

```bash
git clone https://github.com/thinkneo-ai/mcp-server.git
cd mcp-server
pip install -r requirements.txt
pip install -e ".[dev]"

# Install pre-commit hooks (mandatory)
pip install pre-commit
pre-commit install
```

## Security Rules

### NEVER use real credentials in tests

- Test fixtures must use synthetic strings: `FAKE_`, `TEST_`, `NOT_REAL_` prefixes
- API keys in tests: read from `os.environ["THINKNEO_TEST_API_KEY"]`
- Examples of safe test values:
  - `re_FAKE_TEST_KEY_NOT_REAL_00000000000` (not a real Resend key)
  - `sk-FAKE-test-key-not-real-000000` (not a real OpenAI key)
  - `AKIAFAKETEST00000000` (not a real AWS key)
- If you need to test against real services, use environment variables (see `tests/README.md`)

### Pre-commit hooks

Gitleaks runs automatically before each commit. If it flags a false positive:
1. Verify it's actually fake/synthetic
2. Add to `.gitleaksignore` with justification
3. Never suppress a real credential warning

### Before pushing

```bash
pre-commit run --all-files
PYTHONPATH=. pytest tests/unit/ -q
```

## Code Standards

- Python 3.12+
- Type hints on all public functions
- Docstrings on all modules and public functions
- `bandit` HIGH = 0 (enforced by CI)
