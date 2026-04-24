"""Path traversal tests for memory tools."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from tests.conftest import tool_fn, parse_tool_result

PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\etc\\passwd",
    "/etc/passwd",
    "/etc/shadow",
    "....//....//etc/passwd",
    "../../.env",
    "/app/memory/../../.env",
    "test.md/../../../etc/passwd",
]


@pytest.mark.security
@pytest.mark.parametrize("filename", PATH_TRAVERSAL_PAYLOADS)
def test_read_memory_path_traversal(all_tools, filename, tmp_path):
    fn = tool_fn(all_tools, "thinkneo_read_memory")
    with patch("src.tools.memory._MEMORY_DIR", tmp_path):
        result = parse_tool_result(fn(filename=filename))
    # Must NOT return file contents from outside MEMORY_DIR
    assert "content" not in result or result.get("error")


@pytest.mark.security
@pytest.mark.parametrize("filename", PATH_TRAVERSAL_PAYLOADS)
def test_write_memory_path_traversal(all_tools, authenticated, filename, tmp_path):
    fn = tool_fn(all_tools, "thinkneo_write_memory")
    with patch("src.tools.write_memory._MEMORY_DIR", tmp_path):
        result = parse_tool_result(fn(filename=filename, content="# pwned"))
    # File must NOT exist outside MEMORY_DIR
    target = Path("/etc/passwd")
    assert not target.with_suffix(".pwned").exists()
    # If created, must be inside tmp_path
    if "status" in result and result["status"] in ("created", "updated"):
        created_name = result.get("filename", "")
        assert (tmp_path / created_name).exists()
