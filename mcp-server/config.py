from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ServerConfig:
    server_name: str
    server_version: str
    log_level: str
    tools_package: str
    enable_health_tool: bool
    environment: str

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            server_name=os.getenv("VPR_SERVER_NAME", "variant-pathogenicity-rater"),
            server_version=os.getenv("VPR_SERVER_VERSION", "0.2.0-beta"),
            log_level=os.getenv("VPR_LOG_LEVEL", "INFO").upper(),
            tools_package=os.getenv("VPR_TOOLS_PACKAGE", "tools"),
            enable_health_tool=_env_bool("VPR_ENABLE_HEALTH_TOOL", True),
            environment=os.getenv("VPR_ENVIRONMENT", "development"),
        )
