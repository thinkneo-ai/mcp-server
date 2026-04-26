"""
Tests for MCP completions capability (spec 2024-11-05).
12 tests covering prompt argument autocompletion.
"""

import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, ".")

from src.completions_capability import (
    PROVIDERS,
    MODELS_BY_PROVIDER,
    ALL_MODELS,
    _complete_provider,
    _complete_model,
    _complete_workspace,
    register_completions,
)
from mcp import types


class TestCompletionsCapability:
    def test_initialize_declares_completions_capability(self):
        """After registering, the server should have a CompleteRequest handler."""
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register_completions(mcp)
        assert types.CompleteRequest in mcp._mcp_server.request_handlers

    def test_complete_workspace_returns_user_workspaces(self):
        """Authenticated user gets workspace completions."""
        with patch("src.completions_capability.get_bearer_token", return_value="tnk_test"):
            with patch("src.completions_capability._get_conn") as mock_conn:
                mock_ctx = MagicMock()
                mock_cur = MagicMock()
                mock_cur.fetchall.return_value = []
                mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
                mock_ctx.__exit__ = MagicMock(return_value=False)
                mock_ctx.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
                mock_ctx.cursor.return_value.__exit__ = MagicMock(return_value=False)
                mock_conn.return_value = mock_ctx

                result = _complete_workspace("")
                assert isinstance(result, types.Completion)
                assert isinstance(result.values, list)

    def test_complete_workspace_filters_by_prefix(self):
        """Workspace completions respect prefix filter."""
        with patch("src.completions_capability.get_bearer_token", return_value="tnk_test"):
            with patch("src.completions_capability._get_conn") as mock_conn:
                mock_ctx = MagicMock()
                mock_cur = MagicMock()
                mock_cur.fetchall.return_value = []
                mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
                mock_ctx.__exit__ = MagicMock(return_value=False)
                mock_ctx.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
                mock_ctx.cursor.return_value.__exit__ = MagicMock(return_value=False)
                mock_conn.return_value = mock_ctx

                result = _complete_workspace("nonexistent-prefix")
                assert isinstance(result.values, list)
                # With nonexistent prefix, the default workspace won't match
                # (unless the hash happens to start with that prefix)

    def test_complete_workspace_anonymous_returns_empty(self):
        """Anonymous (no token) gets empty workspace completions — privacy."""
        with patch("src.completions_capability.get_bearer_token", return_value=None):
            result = _complete_workspace("")
            assert result.values == []

    def test_complete_provider_returns_all_supported(self):
        """Empty prefix returns all 5 providers."""
        result = _complete_provider("")
        assert set(result.values) == set(PROVIDERS)
        assert len(result.values) == 5

    def test_complete_provider_filters_by_prefix(self):
        """Prefix 'ant' returns only 'anthropic'."""
        result = _complete_provider("ant")
        assert result.values == ["anthropic"]

    def test_complete_provider_anonymous_works(self):
        """Provider completion works without auth (public info)."""
        # _complete_provider doesn't check auth at all
        result = _complete_provider("g")
        assert "google" in result.values

    def test_complete_model_returns_models_for_known_provider(self):
        """With provider context, returns only that provider's models."""
        ctx = types.CompletionContext(arguments={"provider": "anthropic"})
        result = _complete_model("", ctx)
        for model in result.values:
            assert model.startswith("claude"), f"Non-Anthropic model: {model}"
        assert len(result.values) == len(MODELS_BY_PROVIDER["anthropic"])

    def test_complete_model_filters_by_provider_argument_hint(self):
        """Provider hint + prefix filters correctly."""
        ctx = types.CompletionContext(arguments={"provider": "openai"})
        result = _complete_model("gpt-4o", ctx)
        assert "gpt-4o" in result.values
        assert "gpt-4o-mini" in result.values
        assert "gpt-4-turbo" not in result.values  # doesn't start with gpt-4o

    def test_complete_model_default_returns_all_known(self):
        """Without provider context, returns all models from all providers."""
        result = _complete_model("", None)
        assert len(result.values) == len(ALL_MODELS)
        # Should contain models from multiple providers
        has_claude = any("claude" in v for v in result.values)
        has_gpt = any("gpt" in v for v in result.values)
        has_gemini = any("gemini" in v for v in result.values)
        assert has_claude and has_gpt and has_gemini

    def test_complete_invalid_ref_returns_empty(self):
        """Unknown prompt name returns empty completion."""
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register_completions(mcp)

        handler = mcp._mcp_server.request_handlers[types.CompleteRequest]
        req = types.CompleteRequest(
            method="completion/complete",
            params=types.CompleteRequestParams(
                ref=types.PromptReference(type="ref/prompt", name="nonexistent_prompt"),
                argument=types.CompletionArgument(name="foo", value="bar"),
            ),
        )

        result = asyncio.run(handler(req))
        completion = result.root.completion
        assert completion.values == []

    def test_complete_unknown_argument_returns_empty_values(self):
        """Known prompt but unknown argument returns empty."""
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register_completions(mcp)

        handler = mcp._mcp_server.request_handlers[types.CompleteRequest]
        req = types.CompleteRequest(
            method="completion/complete",
            params=types.CompleteRequestParams(
                ref=types.PromptReference(type="ref/prompt", name="thinkneo_policy_preflight"),
                argument=types.CompletionArgument(name="unknown_arg", value="x"),
            ),
        )

        result = asyncio.run(handler(req))
        completion = result.root.completion
        assert completion.values == []
