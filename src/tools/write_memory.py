"""
Tool: thinkneo_write_memory
Writes or updates Claude Code project memory files (.md) in the local memory store.
Public tool — no authentication required.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ._common import utcnow

_MEMORY_DIR = Path("/app/memory")

# Only allow safe filenames: lowercase letters, digits, underscores, hyphens + .md
_SAFE_FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*\.md$")


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="thinkneo_write_memory",
        description=(
            "Write or update a Claude Code project memory file (.md). Persists project context, user preferences, feedback, and reference notes across Claude Code sessions. Filename must end in .md with lowercase alphanumeric characters. Path traversal is blocked. Requires authentication."
            "Use this to persist project context, user preferences, feedback, "
            "and reference notes across Claude Code sessions. "
            "The filename must end in .md and contain only lowercase letters, "
            "digits, underscores, and hyphens (e.g. 'user_fabio.md', "
            "'project_new_feature.md'). Path traversal is blocked."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_write_memory(
        filename: Annotated[
            str,
            Field(
                description=(
                    "Name of the memory file to write (e.g. 'user_fabio.md', "
                    "'project_thinkneodo_droplet.md'). Must end in .md."
                ),
            ),
        ],
        content: Annotated[
            str,
            Field(
                description="Full markdown content to write to the file.",
            ),
        ],
    ) -> str:
        if not _MEMORY_DIR.is_dir():
            return json.dumps(
                {
                    "error": "Memory directory not found",
                    "path": str(_MEMORY_DIR),
                    "timestamp": utcnow(),
                },
                indent=2,
            )

        # Sanitize: strip any directory components
        safe_name = Path(filename).name

        # Validate filename pattern
        if not _SAFE_FILENAME_RE.match(safe_name):
            return json.dumps(
                {
                    "error": (
                        f"Invalid filename: '{safe_name}'. "
                        "Must match pattern: lowercase letters, digits, "
                        "underscores, hyphens, ending in .md "
                        "(e.g. 'user_fabio.md')."
                    ),
                    "timestamp": utcnow(),
                },
                indent=2,
            )

        # Extra guard: resolve and confirm the target stays inside _MEMORY_DIR
        target = (_MEMORY_DIR / safe_name).resolve()
        if not str(target).startswith(str(_MEMORY_DIR.resolve())):
            return json.dumps(
                {
                    "error": "Path traversal blocked",
                    "timestamp": utcnow(),
                },
                indent=2,
            )

        # Reject empty content
        if not content or not content.strip():
            return json.dumps(
                {
                    "error": "Content cannot be empty",
                    "timestamp": utcnow(),
                },
                indent=2,
            )

        is_update = target.is_file()
        target.write_text(content, encoding="utf-8")

        result = {
            "status": "updated" if is_update else "created",
            "filename": safe_name,
            "size_bytes": len(content.encode("utf-8")),
            "timestamp": utcnow(),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
