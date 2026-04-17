"""
Tool: thinkneo_read_memory
Reads Claude Code project memory files (.md) from the local memory store.
Public tool — no authentication required.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

_MEMORY_DIR = Path("/app/memory")

# Strict allowlist: lowercase alphanumerics + _ - . with .md extension.
# Pattern: start with alphanumeric, then alphanumeric/underscore/hyphen/dot, end in .md
# MEMORY.md (uppercase) is an accepted special case (the index file).
_SAFE_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9_\-.]*\.md$")


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
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
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

        # Sanitize: strip any directory components first
        safe_name = Path(filename).name

        # Length check to prevent pathological inputs
        if len(safe_name) > 128:
            return json.dumps(
                {
                    "error": "Filename too long (max 128 chars).",
                    "fetched_at": utcnow(),
                },
                indent=2,
            )

        # Special case: allow MEMORY.md (index) — uppercase exception
        if safe_name != "MEMORY.md" and not _SAFE_FILENAME_RE.match(safe_name):
            return json.dumps(
                {
                    "error": "Invalid filename. Must match: "
                             "lowercase letters, digits, underscores, hyphens, dots, "
                             "ending in '.md' (e.g. 'user_fabio.md').",
                    "got": safe_name[:64],
                    "fetched_at": utcnow(),
                },
                indent=2,
            )

        # Extra guard: resolve paths and confirm target stays within _MEMORY_DIR.
        # Prevents symlink/traversal escapes even if filename sanitization is bypassed.
        try:
            memory_root = _MEMORY_DIR.resolve(strict=True)
            target = (_MEMORY_DIR / safe_name).resolve(strict=False)
            if memory_root not in target.parents and target != memory_root:
                return json.dumps(
                    {
                        "error": "Path traversal blocked.",
                        "fetched_at": utcnow(),
                    },
                    indent=2,
                )
        except (OSError, ValueError):
            return json.dumps(
                {"error": "Could not resolve path.", "fetched_at": utcnow()},
                indent=2,
            )

        if not target.is_file():
            # List available files to help the caller
            available = sorted(
                f.name for f in _MEMORY_DIR.glob("*.md") if f.name != ".git"
            )
            return json.dumps(
                {
                    "error": f"File not found: '{safe_name}'",
                    "available_files": available,
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
