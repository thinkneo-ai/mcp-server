"""
ThinkNEO SDK — Custom exceptions.
"""


class ThinkNEOError(Exception):
    """Base exception for all ThinkNEO SDK errors."""

    def __init__(self, message: str, status_code: int | None = None, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class AuthenticationError(ThinkNEOError):
    """Raised when the API key is missing, invalid, or expired."""


class RateLimitError(ThinkNEOError):
    """Raised when the monthly call limit has been reached."""

    def __init__(self, message: str, tier: str = "free", calls_used: int = 0, monthly_limit: int = 500):
        super().__init__(message)
        self.tier = tier
        self.calls_used = calls_used
        self.monthly_limit = monthly_limit


class ToolError(ThinkNEOError):
    """Raised when a tool call returns an error response."""


class ConnectionError(ThinkNEOError):
    """Raised when the SDK cannot reach the MCP server."""


class ValidationError(ThinkNEOError):
    """Raised for invalid parameters before sending the request."""
