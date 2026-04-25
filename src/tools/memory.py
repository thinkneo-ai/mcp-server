"""
Tool: thinkneo_read_memory
Reads Claude Code project memory files (.md) from the local memory store.
Public tool — no authentication required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

_MEMORY_DIR = Path("/app/memory")


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_read_memory",
        description=(
            "Read Claude Code project memory files. "
            "Without arguments, returns the MEMORY.md index listing all available memories. "
            "With a filename argument, returns the full content of that specific memory file. "
            "Use this to access project context, user preferences, feedback, and reference notes "
            "persisted across Claude Code sessions."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def thinkneo_read_memory(
        filename: Annotated[
            Optional[str],
            Field(
                description=(
                    "Name of the memory file to read (e.g. 'user_fabio.md', "
                    "'project_thinkneodo_droplet.md'). "
                    "Omit to get the MEMORY.md index with all available files."
                ),
            ),
        ] = None,
    ) -> str:
        if not _MEMORY_DIR.is_dir():
            return json.dumps(
                {
                    "error": "Memory directory not found",
                    "path": str(_MEMORY_DIR),
                    "fetched_at": utcnow(),
                },
                indent=2,
            )

        # Default: return the index
        if not filename:
            filename = "MEMORY.md"

        # Sanitize: only allow .md files, no path traversal
        safe_name = Path(filename).name
        if not safe_name.endswith(".md"):
            return json.dumps(
                {
                    "error": f"Only .md files are supported, got: '{safe_name}'",
                    "fetched_at": utcnow(),
                },
                indent=2,
            )

        target = (_MEMORY_DIR / safe_name).resolve()
        # Guard against symlink-based path traversal
        if not str(target).startswith(str(_MEMORY_DIR.resolve())):
            return json.dumps(
                {
                    "error": "Path traversal blocked",
                    "fetched_at": utcnow(),
                },
                indent=2,
            )

        if not target.is_file():
            return json.dumps(
                {
                    "error": f"File not found: '{safe_name}'",
                    "hint": "Use thinkneo_read_memory without arguments to get the MEMORY.md index.",
                    "fetched_at": utcnow(),
                },
                indent=2,
            )

        content = target.read_text(encoding="utf-8")

        result = {
            "filename": safe_name,
            "content": content,
            "size_bytes": len(content.encode("utf-8")),
            "fetched_at": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
