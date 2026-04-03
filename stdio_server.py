"""Stdio entry point for Glama inspection and mcp-proxy."""
from src.server import mcp

mcp.run(transport="stdio")
