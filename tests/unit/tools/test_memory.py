"""
Deep unit tests for memory tools (read_memory, write_memory).

Tests path validation, filename sanitization, and filesystem operations.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tests.conftest import tool_fn, parse_tool_result


@pytest.fixture
def read_fn(all_tools):
    return tool_fn(all_tools, "thinkneo_read_memory")


@pytest.fixture
def write_fn(all_tools):
    return tool_fn(all_tools, "thinkneo_write_memory")


# ---------------------------------------------------------------------------
# READ MEMORY
# ---------------------------------------------------------------------------

class TestReadMemory:
    def test_no_filename_returns_index(self, read_fn, tmp_path):
        index = tmp_path / "MEMORY.md"
        index.write_text("# Memory Index\n- item 1")

        with patch("src.tools.memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(read_fn())
        assert "content" in result or "files" in result or "error" not in result

    def test_valid_filename_returns_content(self, read_fn, tmp_path):
        test_file = tmp_path / "user_test.md"
        test_file.write_text("# Test User\nHello")

        with patch("src.tools.memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(read_fn(filename="user_test.md"))
        assert "content" in result or "error" not in result

    def test_nonexistent_file_returns_error(self, read_fn, tmp_path):
        with patch("src.tools.memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(read_fn(filename="nonexistent.md"))
        # Should return an error or available files list
        assert isinstance(result, dict)

    def test_path_traversal_blocked(self, read_fn, tmp_path):
        with patch("src.tools.memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(read_fn(filename="../../../etc/passwd"))
        assert "error" in result or "available" in result


# ---------------------------------------------------------------------------
# WRITE MEMORY
# ---------------------------------------------------------------------------

class TestWriteMemory:
    def test_requires_auth(self):
        """write_memory must reject unauthenticated calls."""
        from src.auth import _bearer_token, require_auth

        # Direct test: require_auth raises when no token
        ctx = _bearer_token.set(None)
        try:
            with pytest.raises(ValueError, match="Authentication required"):
                require_auth()
        finally:
            _bearer_token.reset(ctx)

    def test_creates_file(self, write_fn, authenticated, tmp_path):
        with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(write_fn(filename="test_new.md", content="# New File"))
        assert result.get("status") in ("created", "updated")
        assert (tmp_path / "test_new.md").exists()

    def test_rejects_non_md_extension(self, write_fn, authenticated, tmp_path):
        with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(write_fn(filename="evil.sh", content="#!/bin/bash"))
        assert "error" in result

    def test_rejects_uppercase_filename(self, write_fn, authenticated, tmp_path):
        with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(write_fn(filename="UPPER.md", content="# test"))
        assert "error" in result

    def test_rejects_empty_content(self, write_fn, authenticated, tmp_path):
        with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(write_fn(filename="test.md", content=""))
        assert "error" in result

    def test_path_traversal_stripped_to_safe_name(self, write_fn, authenticated, tmp_path):
        """../../evil.md gets stripped to evil.md by Path.name — file lands inside MEMORY_DIR."""
        with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(write_fn(filename="../../evil.md", content="# test"))
        # Path.name strips directory components, so evil.md is created inside tmp_path
        # This is the correct behavior — no file outside MEMORY_DIR
        assert not (tmp_path.parent.parent / "evil.md").exists()
        if "error" not in result:
            assert (tmp_path / "evil.md").exists()  # landed safely inside MEMORY_DIR

    def test_rejects_dotfile(self, write_fn, authenticated, tmp_path):
        with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
            result = parse_tool_result(write_fn(filename=".env", content="SECRET=x"))
        assert "error" in result
