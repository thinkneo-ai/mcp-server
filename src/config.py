"""
Configuration — ThinkNEO MCP Server
Settings loaded from environment / .env file.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional


class Settings:
    def __init__(self) -> None:
        # Server
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8081"))
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

        # Auth — comma-separated list of valid API keys
        self.api_keys_raw: str = os.getenv("THINKNEO_MCP_API_KEYS", "")
        # Master key (always valid if set)
        self.master_key: str = os.getenv("THINKNEO_API_KEY", "")

        # Optional: internal ThinkNEO governance API base URL
        # If set, tools will call this API instead of using embedded logic.
        self.thinkneo_api_base_url: Optional[str] = os.getenv("THINKNEO_API_BASE_URL")

        # CORS origins (comma-separated)
        self.allowed_origins_raw: str = os.getenv(
            "ALLOWED_ORIGINS",
            "https://claude.ai,https://chatgpt.com,https://copilot.microsoft.com",
        )

        # Scheduling — where to send demo requests
        self.demo_webhook_url: Optional[str] = os.getenv("DEMO_WEBHOOK_URL")
        self.demo_email: str = os.getenv("DEMO_EMAIL", "hello@thinkneo.ai")

        # Public URL (shown in docs / error messages)
        self.public_url: str = os.getenv("PUBLIC_URL", "https://mcp.thinkneo.ai")

    @property
    def valid_api_keys(self) -> set[str]:
        keys: set[str] = set()
        if self.api_keys_raw:
            keys.update(k.strip() for k in self.api_keys_raw.split(",") if k.strip())
        if self.master_key:
            keys.add(self.master_key)
        return keys

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]

    @property
    def require_auth(self) -> bool:
        """True if at least one API key is configured."""
        return bool(self.valid_api_keys)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
