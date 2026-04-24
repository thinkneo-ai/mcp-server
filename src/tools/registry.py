"""
Tools: thinkneo_registry_*
MCP Marketplace Registry — discover, publish, install, and review MCP servers.
The "npm for MCP tools".
"""

from __future__ import annotations

import json
from typing import Annotated, List, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..auth import get_bearer_token, require_auth
from ..database import hash_key
from ..marketplace import (
    VALID_CATEGORIES,
    add_review,
    get_registry_entry,
    publish_to_registry,
    search_registry,
    track_install,
)
from ._common import utcnow


def register(mcp: FastMCP) -> None:
    # ── 1. Search ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="thinkneo_registry_search",
        description=(
            "Search the ThinkNEO MCP Marketplace — the npm for MCP tools. "
            "Discover MCP servers and tools by keyword, category, rating, or verified status. "
            "Returns name, description, tools count, rating, downloads, and verified badge. "
            "No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_registry_search(
        query: Annotated[str, Field(description="Search query — matches name, description, tags, and tool names")] = "",
        category: Annotated[Optional[str], Field(description=f"Filter by category: {', '.join(VALID_CATEGORIES)}")] = None,
        min_rating: Annotated[Optional[float], Field(description="Minimum average rating (1.0-5.0)")] = None,
        verified_only: Annotated[bool, Field(description="If true, return only verified packages")] = False,
        limit: Annotated[int, Field(description="Max results to return (1-100, default 20)")] = 20,
    ) -> str:
        results = search_registry(
            query=query,
            category=category,
            min_rating=min_rating,
            verified_only=verified_only,
            limit=limit,
        )

        # Trim output to essential fields
        packages = []
        for r in results:
            packages.append({
                "name": r.get("name"),
                "display_name": r.get("display_name"),
                "description": r.get("description", "")[:300],
                "version": r.get("version"),
                "transport": r.get("transport"),
                "tools_count": r.get("tools_count", 0),
                "categories": r.get("categories", []),
                "avg_rating": float(r.get("avg_rating", 0)),
                "review_count": int(r.get("review_count", 0)),
                "downloads": r.get("downloads", 0),
                "verified": r.get("verified", False),
                "security_score": r.get("security_score"),
                "author": r.get("author", ""),
            })

        output = {
            "query": query,
            "category": category,
            "total_results": len(packages),
            "packages": packages,
            "registry_url": "https://mcp.thinkneo.ai/registry",
            "searched_at": utcnow(),
        }
        return json.dumps(output, indent=2, ensure_ascii=False, default=str)

    # ── 2. Get Details ────────────────────────────────────────────────────────
    @mcp.tool(
        name="thinkneo_registry_get",
        description=(
            "Get full details for an MCP server package from the ThinkNEO Marketplace. "
            "Returns readme, full tools list, version history, reviews, security score, "
            "and installation instructions. No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    def thinkneo_registry_get(
        name: Annotated[str, Field(description="Package name (e.g. 'thinkneo-control-plane', 'filesystem', 'github')")],
    ) -> str:
        entry = get_registry_entry(name)
        if not entry:
            return json.dumps({
                "error": f"Package '{name}' not found in the registry",
                "hint": "Use thinkneo_registry_search to find available packages",
                "registry_url": "https://mcp.thinkneo.ai/registry",
            }, indent=2)

        # Remove internal fields
        entry.pop("id", None)

        output = {
            "package": entry,
            "install_hint": f"Use thinkneo_registry_install with name='{name}' to get installation config",
            "registry_url": "https://mcp.thinkneo.ai/registry",
            "fetched_at": utcnow(),
        }
        return json.dumps(output, indent=2, ensure_ascii=False, default=str)

    # ── 3. Publish ────────────────────────────────────────────────────────────
    @mcp.tool(
        name="thinkneo_registry_publish",
        description=(
            "Publish an MCP server to the ThinkNEO Marketplace. "
            "Validates the endpoint (calls initialize + tools/list), runs security scan "
            "(secrets detection, injection patterns), and stores the entry. "
            "Authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_registry_publish(
        name: Annotated[str, Field(description="Package name (lowercase, hyphens allowed, e.g. 'my-mcp-server')")],
        display_name: Annotated[str, Field(description="Human-readable display name")],
        description: Annotated[str, Field(description="Short description of what this MCP server does (max 500 chars)")],
        endpoint_url: Annotated[str, Field(description="MCP server endpoint URL (e.g. https://my-server.com/mcp)")],
        transport: Annotated[str, Field(description="Transport type: streamable-http, sse, or stdio")] = "streamable-http",
        categories: Annotated[Optional[List[str]], Field(description=f"Categories: {', '.join(VALID_CATEGORIES)}")] = None,
        tags: Annotated[Optional[List[str]], Field(description="Tags for discoverability (e.g. ['ai', 'governance', 'security'])")] = None,
        repo_url: Annotated[str, Field(description="Source code repository URL")] = "",
        license: Annotated[str, Field(description="License (e.g. MIT, Apache-2.0)")] = "MIT",
        readme: Annotated[str, Field(description="Full readme/documentation in markdown")] = "",
    ) -> str:
        # Auth check
        token = require_auth()
        key_h = hash_key(token)

        result = publish_to_registry(
            name=name,
            display_name=display_name,
            description=description[:500],
            endpoint_url=endpoint_url,
            transport=transport,
            categories=categories,
            tags=tags,
            repo_url=repo_url,
            license_=license,
            readme=readme[:50000],
            author=token[:8] + "...",  # Use key prefix as author identifier
            owner_key_hash=key_h,
        )

        if "error" in result:
            return json.dumps(result, indent=2)

        # Clean for output
        result.pop("id", None)

        output = {
            "status": "published",
            "package": result,
            "registry_url": f"https://mcp.thinkneo.ai/registry",
            "published_at": utcnow(),
        }
        return json.dumps(output, indent=2, ensure_ascii=False, default=str)

    # ── 4. Review ─────────────────────────────────────────────────────────────
    @mcp.tool(
        name="thinkneo_registry_review",
        description=(
            "Rate and review an MCP server in the ThinkNEO Marketplace. "
            "One review per user per package (updates on repeat). "
            "Authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    )
    def thinkneo_registry_review(
        name: Annotated[str, Field(description="Package name to review")],
        rating: Annotated[int, Field(description="Rating from 1 (poor) to 5 (excellent)")],
        comment: Annotated[str, Field(description="Review comment (max 2000 chars)")] = "",
    ) -> str:
        token = require_auth()
        key_h = hash_key(token)

        result = add_review(
            name=name,
            api_key_hash=key_h,
            rating=rating,
            comment=comment,
        )

        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    # ── 5. Install ────────────────────────────────────────────────────────────
    @mcp.tool(
        name="thinkneo_registry_install",
        description=(
            "Get installation config for an MCP server from the ThinkNEO Marketplace. "
            "Returns ready-to-use JSON config for Claude Desktop, Cursor, Windsurf, or custom clients. "
            "Tracks the download. No authentication required."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False),
    )
    def thinkneo_registry_install(
        name: Annotated[str, Field(description="Package name to install (e.g. 'thinkneo-control-plane')")],
        client_type: Annotated[str, Field(description="Your MCP client: claude-desktop, cursor, windsurf, or custom")] = "claude-desktop",
    ) -> str:
        token = get_bearer_token()
        key_h = hash_key(token) if token else "anonymous"

        result = track_install(
            name=name,
            client_type=client_type,
            api_key_hash=key_h,
        )

        if not result:
            return json.dumps({
                "error": f"Package '{name}' not found in the registry",
                "hint": "Use thinkneo_registry_search to find available packages",
            }, indent=2)

        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
