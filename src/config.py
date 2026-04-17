"""
Configuration — all sensitive values from environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8081
    log_level: str = "INFO"
    require_auth: bool = True
    valid_api_keys: List[str] = field(default_factory=list)
    allowed_origins: List[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw_keys = os.getenv("THINKNEO_MCP_API_KEYS", "")
    master_key = os.getenv("THINKNEO_API_KEY", "")
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if master_key and master_key not in keys:
        keys.append(master_key)

    raw_origins = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    return Settings(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8081")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        require_auth=bool(keys),
        valid_api_keys=keys,
        allowed_origins=origins,
    )
