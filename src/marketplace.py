"""
ThinkNEO MCP Marketplace — Registry Engine

Core logic for publishing, searching, installing, and reviewing MCP servers.
This is the "npm for MCP tools" — a public registry where anyone can discover,
publish, and install MCP servers and tools.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import ipaddress
from urllib.parse import urlparse

import httpx
import psycopg
from psycopg.rows import dict_row

from .database import _get_conn, hash_key

logger = logging.getLogger(__name__)

# ── Valid categories ──────────────────────────────────────────────────────────
VALID_CATEGORIES = [
    "governance", "security", "data", "development", "productivity",
    "communication", "analytics", "devops", "finance", "marketing", "other",
]

# ── Injection patterns (reused from guardrails_free) ──────────────────────────
_INJECTION_PATTERNS = [
    r"ignore\b.{0,30}\b(previous|prior|above|all|earlier)\b.{0,30}\binstructions?",
    r"disregard\b.{0,40}\b(system|previous|prior|instructions?|rules?)",
    r"(you are|act as|pretend to be)\b.{0,30}\b(DAN|unrestricted|jailbreak|evil|uncensored)",
    r"(new|override|updated)\s+(system\s+)?(instructions?|prompt|rules?):",
    r"forget\b.{0,30}\b(everything|all|what you were|your (instructions|rules|training))",
    r"reveal\b.{0,30}\b(system\s+prompt|instructions?|hidden|secret)",
]

# Secret-like patterns
_SECRET_PATTERNS = [
    r"(?:password|passwd|pwd|secret)\s*[:=]\s*\S+",
    r"(?:api[_-]?key|token|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{20,}",
    r"-----BEGIN (?:RSA|DSA|EC|OPENSSH) PRIVATE KEY-----",
    r"(?:sk|pk|rk)-[a-zA-Z0-9]{32,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"gho_[a-zA-Z0-9]{36}",
    r"AKIA[0-9A-Z]{16}",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Security Scanning ─────────────────────────────────────────────────────────

def _scan_text_for_secrets(text: str) -> List[str]:
    """Scan text for secret/credential patterns."""
    findings = []
    for pattern in _SECRET_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            findings.append(f"Secret pattern matched: {pattern[:50]}...")
    return findings


def _scan_text_for_injection(text: str) -> List[str]:
    """Scan text for prompt injection patterns."""
    findings = []
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            findings.append(f"Injection pattern matched: {pattern[:50]}...")
    return findings


def _compute_security_score(
    tool_descriptions: List[str],
    readme: str,
    endpoint_reachable: bool,
) -> tuple[int, List[str]]:
    """
    Compute a security score (0-100) for an MCP server.
    Returns (score, findings).
    """
    score = 100
    findings: List[str] = []

    # Check tool descriptions for secrets
    all_text = " ".join(tool_descriptions) + " " + readme
    secret_hits = _scan_text_for_secrets(all_text)
    if secret_hits:
        score -= 30
        findings.extend(secret_hits)

    # Check for injection patterns in tool descriptions
    injection_hits = _scan_text_for_injection(all_text)
    if injection_hits:
        score -= 25
        findings.extend(injection_hits)

    # Endpoint not reachable → penalty
    if not endpoint_reachable:
        score -= 15
        findings.append("Endpoint not reachable at publish time")

    # No HTTPS → penalty
    # (checked in the caller via endpoint_url)

    return max(0, score), findings


# ── URL Safety ────────────────────────────────────────────────────────────────

def _is_safe_url(url: str) -> tuple[bool, str]:
    """
    Reject URLs that point to private/internal networks (SSRF protection).
    Returns (is_safe, reason).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname or ""

    # Block obvious internal hostnames
    blocked_hostnames = {
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "metadata.google.internal",
        "169.254.169.254",  # AWS/GCP metadata
    }
    if hostname.lower() in blocked_hostnames:
        return False, f"Blocked hostname: {hostname}"

    # Block private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"Private/reserved IP blocked: {hostname}"
    except ValueError:
        # hostname is a domain, not an IP — that's fine
        pass

    # Block internal-looking domains
    if hostname.endswith(".internal") or hostname.endswith(".local"):
        return False, f"Internal domain blocked: {hostname}"

    return True, "ok"


# ── Endpoint Validation ──────────────────────────────────────────────────────

def _validate_endpoint(endpoint_url: str, transport: str) -> tuple[bool, List[Dict[str, Any]]]:
    """
    Validate an MCP server endpoint by calling initialize + tools/list.
    Returns (success, tools_list).
    """
    if transport == "stdio":
        # Cannot remotely validate stdio servers
        return True, []

    # SSRF protection — block private/internal URLs
    url_safe, reason = _is_safe_url(endpoint_url)
    if not url_safe:
        logger.warning("Endpoint URL blocked (SSRF): %s — %s", endpoint_url, reason)
        return False, []

    try:
        with httpx.Client(timeout=15.0) as client:
            # Step 1: Initialize
            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": 1,
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "thinkneo-registry", "version": "1.0.0"},
                },
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            resp = client.post(endpoint_url, json=init_payload, headers=headers)

            if resp.status_code not in (200, 202):
                logger.warning("Endpoint %s returned status %d on initialize", endpoint_url, resp.status_code)
                return False, []

            # Try to extract session-id from response headers for subsequent requests
            session_id = resp.headers.get("mcp-session-id", "")
            if session_id:
                headers["mcp-session-id"] = session_id

            # Step 2: Send initialized notification
            notif_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            client.post(endpoint_url, json=notif_payload, headers=headers)

            # Step 3: tools/list
            tools_payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2,
                "params": {},
            }
            resp2 = client.post(endpoint_url, json=tools_payload, headers=headers)

            if resp2.status_code not in (200, 202):
                logger.warning("Endpoint %s returned status %d on tools/list", endpoint_url, resp2.status_code)
                return True, []  # Initialize worked, tools/list didn't

            # Parse tools from response
            try:
                body = resp2.json()
                if isinstance(body, dict) and "result" in body:
                    tools_raw = body["result"].get("tools", [])
                    tools = []
                    for t in tools_raw:
                        tools.append({
                            "name": t.get("name", ""),
                            "description": t.get("description", "")[:500],
                        })
                    return True, tools
            except Exception:
                pass

            return True, []

    except httpx.TimeoutException:
        logger.warning("Endpoint %s timed out during validation", endpoint_url)
        return False, []
    except Exception as exc:
        logger.warning("Endpoint validation failed for %s: %s", endpoint_url, exc)
        return False, []


# ── Database Operations ──────────────────────────────────────────────────────

def search_registry(
    query: str = "",
    category: Optional[str] = None,
    min_rating: Optional[float] = None,
    verified_only: bool = False,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Search the MCP registry with full-text search and filters."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                conditions = []
                params: List[Any] = []

                # Full-text search
                if query and query.strip():
                    conditions.append(
                        "to_tsvector('english', coalesce(name, '') || ' ' || coalesce(display_name, '') || ' ' || coalesce(description, '')) @@ plainto_tsquery('english', %s)"
                    )
                    params.append(query.strip())

                # Category filter
                if category and category in VALID_CATEGORIES:
                    conditions.append("%s = ANY(categories)")
                    params.append(category)

                # Verified filter
                if verified_only:
                    conditions.append("verified = TRUE")

                where = ""
                if conditions:
                    where = "WHERE " + " AND ".join(conditions)

                # Limit
                limit = min(max(1, limit), 100)
                params.append(limit)

                sql = f"""
                    SELECT r.*,
                           COALESCE(
                               (SELECT ROUND(AVG(rating)::numeric, 1) FROM mcp_registry_reviews WHERE registry_id = r.id),
                               0
                           ) AS avg_rating,
                           COALESCE(
                               (SELECT COUNT(*) FROM mcp_registry_reviews WHERE registry_id = r.id),
                               0
                           ) AS review_count
                    FROM mcp_registry r
                    {where}
                    ORDER BY r.verified DESC, r.downloads DESC, r.stars DESC
                    LIMIT %s
                """

                cur.execute(sql, params)
                rows = cur.fetchall()

                # Apply min_rating filter in Python (simpler than sub-query filter)
                results = []
                for row in rows:
                    row_dict = dict(row)
                    if min_rating and float(row_dict.get("avg_rating", 0)) < min_rating:
                        continue
                    # Clean up for JSON serialization
                    for key in ("created_at", "updated_at", "published_at"):
                        if row_dict.get(key):
                            row_dict[key] = row_dict[key].isoformat()
                    results.append(row_dict)

                return results
    except Exception as exc:
        logger.error("search_registry failed: %s", exc)
        return []


def get_registry_entry(name: str) -> Optional[Dict[str, Any]]:
    """Get full details for a registry entry by name."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT r.*,
                           COALESCE(
                               (SELECT ROUND(AVG(rating)::numeric, 1) FROM mcp_registry_reviews WHERE registry_id = r.id),
                               0
                           ) AS avg_rating,
                           COALESCE(
                               (SELECT COUNT(*) FROM mcp_registry_reviews WHERE registry_id = r.id),
                               0
                           ) AS review_count
                    FROM mcp_registry r
                    WHERE r.name = %s
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                entry = dict(row)

                # Get versions
                cur.execute(
                    """
                    SELECT version, changelog, tools_list, created_at
                    FROM mcp_registry_versions
                    WHERE registry_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    (entry["id"],),
                )
                versions = []
                for v in cur.fetchall():
                    vd = dict(v)
                    if vd.get("created_at"):
                        vd["created_at"] = vd["created_at"].isoformat()
                    versions.append(vd)
                entry["versions"] = versions

                # Get recent reviews
                cur.execute(
                    """
                    SELECT rating, comment, created_at
                    FROM mcp_registry_reviews
                    WHERE registry_id = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    (entry["id"],),
                )
                reviews = []
                for rv in cur.fetchall():
                    rvd = dict(rv)
                    if rvd.get("created_at"):
                        rvd["created_at"] = rvd["created_at"].isoformat()
                    reviews.append(rvd)
                entry["recent_reviews"] = reviews

                # Serialize timestamps
                for key in ("created_at", "updated_at", "published_at"):
                    if entry.get(key):
                        entry[key] = entry[key].isoformat()

                return entry
    except Exception as exc:
        logger.error("get_registry_entry failed: %s", exc)
        return None


def publish_to_registry(
    name: str,
    display_name: str,
    description: str,
    endpoint_url: str,
    transport: str = "streamable-http",
    categories: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    repo_url: str = "",
    license_: str = "MIT",
    readme: str = "",
    author: str = "",
    author_email: str = "",
    icon_url: str = "",
    owner_key_hash: str = "",
) -> Dict[str, Any]:
    """
    Publish or update an MCP server in the registry.
    Validates the endpoint, runs security scans, and stores the entry.
    """
    # Normalize name
    name = re.sub(r"[^a-z0-9\-]", "-", name.lower().strip())[:100]
    if not name:
        return {"error": "Invalid package name"}

    # Validate transport
    if transport not in ("streamable-http", "sse", "stdio"):
        return {"error": f"Invalid transport: {transport}. Must be streamable-http, sse, or stdio"}

    # Validate categories
    cats = [c for c in (categories or []) if c in VALID_CATEGORIES] or ["other"]

    # Validate endpoint
    endpoint_reachable, discovered_tools = _validate_endpoint(endpoint_url, transport)

    # Use discovered tools if available
    tools_list = discovered_tools if discovered_tools else []
    tools_count = len(tools_list)

    # Security scan
    tool_descriptions = [t.get("description", "") for t in tools_list]
    security_score, security_findings = _compute_security_score(
        tool_descriptions, readme or "", endpoint_reachable
    )

    # HTTPS check
    if not endpoint_url.startswith("https://") and transport != "stdio":
        security_score = max(0, security_score - 10)
        security_findings.append("Endpoint does not use HTTPS")

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Ownership check — if package exists, only the owner can update
                if owner_key_hash:
                    cur.execute(
                        "SELECT owner_key_hash FROM mcp_registry WHERE name = %s",
                        (name,),
                    )
                    existing = cur.fetchone()
                    if existing and existing["owner_key_hash"] and existing["owner_key_hash"] != owner_key_hash:
                        return {"error": f"Package '{name}' is owned by another user. You cannot overwrite it."}

                # Upsert
                cur.execute(
                    """
                    INSERT INTO mcp_registry (
                        name, display_name, description, author, author_email,
                        version, endpoint_url, transport, tools_count, tools_list,
                        categories, tags, readme, icon_url, repo_url, license,
                        verified, security_score, owner_key_hash, updated_at, published_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        '1.0.0', %s, %s, %s, %s::jsonb,
                        %s, %s, %s, %s, %s, %s,
                        FALSE, %s, %s, NOW(), NOW()
                    )
                    ON CONFLICT (name) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        description = EXCLUDED.description,
                        author = EXCLUDED.author,
                        author_email = EXCLUDED.author_email,
                        endpoint_url = EXCLUDED.endpoint_url,
                        transport = EXCLUDED.transport,
                        tools_count = EXCLUDED.tools_count,
                        tools_list = EXCLUDED.tools_list,
                        categories = EXCLUDED.categories,
                        tags = EXCLUDED.tags,
                        readme = EXCLUDED.readme,
                        icon_url = EXCLUDED.icon_url,
                        repo_url = EXCLUDED.repo_url,
                        license = EXCLUDED.license,
                        security_score = EXCLUDED.security_score,
                        updated_at = NOW()
                    RETURNING *
                    """,
                    (
                        name, display_name, description, author, author_email,
                        endpoint_url, transport, tools_count, json.dumps(tools_list),
                        cats, tags or [], readme or "", icon_url, repo_url, license_,
                        security_score, owner_key_hash,
                    ),
                )
                row = cur.fetchone()
                entry = dict(row)

                # Record version
                cur.execute(
                    """
                    INSERT INTO mcp_registry_versions (registry_id, version, changelog, tools_list)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (entry["id"], entry["version"], "Initial publish", json.dumps(tools_list)),
                )

                # Serialize timestamps
                for key in ("created_at", "updated_at", "published_at"):
                    if entry.get(key):
                        entry[key] = entry[key].isoformat()

                entry["_security"] = {
                    "score": security_score,
                    "findings": security_findings,
                    "endpoint_reachable": endpoint_reachable,
                    "tools_discovered": tools_count,
                }

                return entry

    except Exception as exc:
        logger.error("publish_to_registry failed: %s", exc)
        return {"error": f"Failed to publish: {exc}"}


def add_review(
    name: str,
    api_key_hash: str,
    rating: int,
    comment: str = "",
) -> Dict[str, Any]:
    """Add or update a review for a registry entry."""
    if rating < 1 or rating > 5:
        return {"error": "Rating must be between 1 and 5"}

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Get registry entry
                cur.execute("SELECT id FROM mcp_registry WHERE name = %s", (name,))
                row = cur.fetchone()
                if not row:
                    return {"error": f"Package '{name}' not found"}

                registry_id = row["id"]

                # Upsert review
                cur.execute(
                    """
                    INSERT INTO mcp_registry_reviews (registry_id, api_key_hash, rating, comment)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (registry_id, api_key_hash) DO UPDATE SET
                        rating = EXCLUDED.rating,
                        comment = EXCLUDED.comment,
                        created_at = NOW()
                    RETURNING *
                    """,
                    (registry_id, api_key_hash, rating, comment[:2000]),
                )
                review = dict(cur.fetchone())

                # Get new average
                cur.execute(
                    "SELECT ROUND(AVG(rating)::numeric, 1) as avg, COUNT(*) as cnt FROM mcp_registry_reviews WHERE registry_id = %s",
                    (registry_id,),
                )
                stats = cur.fetchone()

                if review.get("created_at"):
                    review["created_at"] = review["created_at"].isoformat()

                return {
                    "status": "ok",
                    "package": name,
                    "your_rating": rating,
                    "average_rating": float(stats["avg"]) if stats["avg"] else 0,
                    "total_reviews": stats["cnt"],
                    "created_at": review["created_at"],
                }
    except Exception as exc:
        logger.error("add_review failed: %s", exc)
        return {"error": f"Failed to add review: {exc}"}


def track_install(
    name: str,
    client_type: str = "custom",
    api_key_hash: str = "anonymous",
) -> Optional[Dict[str, Any]]:
    """
    Track an install and return installation config for the client.
    Increments the download counter.
    """
    valid_clients = ("claude-desktop", "cursor", "windsurf", "custom")
    if client_type not in valid_clients:
        client_type = "custom"

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                # Get entry
                cur.execute(
                    "SELECT * FROM mcp_registry WHERE name = %s",
                    (name,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                entry = dict(row)

                # Increment downloads
                cur.execute(
                    "UPDATE mcp_registry SET downloads = downloads + 1 WHERE id = %s",
                    (entry["id"],),
                )

                # Record install
                cur.execute(
                    """
                    INSERT INTO mcp_registry_installs (registry_id, api_key_hash, client_type)
                    VALUES (%s, %s, %s)
                    """,
                    (entry["id"], api_key_hash, client_type),
                )

                # Generate install config based on client type
                endpoint = entry["endpoint_url"]
                transport = entry["transport"]
                pkg_name = entry["name"]

                config = _generate_install_config(
                    pkg_name, endpoint, transport, client_type
                )

                return {
                    "package": pkg_name,
                    "version": entry["version"],
                    "transport": transport,
                    "endpoint": endpoint,
                    "client_type": client_type,
                    "downloads": entry["downloads"] + 1,
                    "install_config": config,
                    "installed_at": _utcnow(),
                }
    except Exception as exc:
        logger.error("track_install failed: %s", exc)
        return None


def _generate_install_config(
    name: str, endpoint: str, transport: str, client_type: str
) -> Dict[str, Any]:
    """Generate client-specific installation config."""
    if transport == "stdio":
        # stdio servers need npx or command
        base_config = {
            "command": "npx",
            "args": [f"@modelcontextprotocol/server-{name}"],
        }
    else:
        base_config = {
            "url": endpoint,
        }

    if client_type == "claude-desktop":
        return {
            "config_file": "~/.claude/claude_desktop_config.json",
            "config": {
                "mcpServers": {
                    name: base_config
                }
            },
            "instructions": f"Add to your claude_desktop_config.json under mcpServers."
        }
    elif client_type == "cursor":
        return {
            "config_file": ".cursor/mcp.json",
            "config": {
                "mcpServers": {
                    name: base_config
                }
            },
            "instructions": f"Add to .cursor/mcp.json in your project root."
        }
    elif client_type == "windsurf":
        return {
            "config_file": "~/.codeium/windsurf/mcp_config.json",
            "config": {
                "mcpServers": {
                    name: base_config
                }
            },
            "instructions": f"Add to your Windsurf MCP config."
        }
    else:
        return {
            "endpoint": endpoint,
            "transport": transport,
            "instructions": (
                f"Connect to {endpoint} using {transport} transport. "
                "Include Authorization: Bearer YOUR_API_KEY header if auth is required."
            ),
        }
