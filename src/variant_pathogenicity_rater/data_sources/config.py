from __future__ import annotations

import os
from enum import StrEnum
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel


class ProviderMode(StrEnum):
    MOCK = "mock"
    LOCAL_FILE = "local_file"
    ONLINE_DISABLED = "online_disabled"
    FUTURE_ONLINE = "future_online"
    ONLINE = "online"


class DataSourceConfig(SchemaModel):
    name: str = Field(..., min_length=1)
    mode: ProviderMode = ProviderMode.MOCK
    enabled: bool = True
    online_enabled: bool = False
    source_version: str | None = None
    parser_version: str = "v1"
    ttl_seconds: int | None = Field(default=86400, ge=0)
    cache_dir: str | None = ".cache/variant_pathogenicity_rater"
    local_file: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)
    retry_count: int = Field(default=0, ge=0)
    retry_backoff_seconds: float = Field(default=0.25, ge=0)
    user_agent: str | None = None
    email: str | None = None
    limitations: list[str] = Field(default_factory=list)


class DataSourcesConfig(SchemaModel):
    default_mode: ProviderMode = ProviderMode.MOCK
    offline_default: bool = True
    sources: dict[str, DataSourceConfig] = Field(default_factory=dict)

    def source(self, name: str) -> DataSourceConfig:
        return self.sources.get(
            name,
            DataSourceConfig(
                name=name,
                mode=self.default_mode,
                limitations=["No source-specific configuration was found; using offline default."],
            ),
        )


DEFAULT_SOURCE_NAMES = (
    "clinvar",
    "population",
    "literature",
    "computational",
    "clingen_erepo",
    "clingen_allele_registry",
)


def default_data_sources_config() -> DataSourcesConfig:
    return DataSourcesConfig(
        sources={
            name: DataSourceConfig(
                name=name,
                mode=ProviderMode.MOCK,
                source_version="offline-fixture-v1",
                parser_version="v1",
                limitations=["Default offline mock mode; no external network access is permitted."],
            )
            for name in DEFAULT_SOURCE_NAMES
        }
    )


def load_data_sources_config(
    *,
    overrides: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> DataSourcesConfig:
    config = _load_packaged_config()
    if overrides:
        config = _merge_overrides(config, overrides)
    return _apply_env_overrides(config, env or os.environ)


def _load_packaged_config() -> DataSourcesConfig:
    try:
        config_path = resources.files("variant_pathogenicity_rater.config").joinpath(
            "data_sources.yaml"
        )
        return _parse_simple_yaml_config(Path(str(config_path)))
    except Exception:
        return default_data_sources_config()


def _merge_overrides(config: DataSourcesConfig, overrides: dict[str, Any]) -> DataSourcesConfig:
    payload = config.model_dump(mode="json")
    for top_key in ("default_mode", "offline_default"):
        if top_key in overrides:
            payload[top_key] = overrides[top_key]
    source_overrides = overrides.get("sources") or overrides.get("data_sources") or {}
    for name, source_override in source_overrides.items():
        current = payload["sources"].get(name, {"name": name})
        current.update(source_override or {})
        current.setdefault("name", name)
        payload["sources"][name] = current
    for name in DEFAULT_SOURCE_NAMES:
        if name in overrides and isinstance(overrides[name], dict):
            current = payload["sources"].get(name, {"name": name})
            current.update(overrides[name])
            current.setdefault("name", name)
            payload["sources"][name] = current
    return DataSourcesConfig.model_validate(payload)


def _apply_env_overrides(config: DataSourcesConfig, env: dict[str, str]) -> DataSourcesConfig:
    payload = config.model_dump(mode="json")
    if env.get("VPR_DATA_SOURCE_MODE"):
        payload["default_mode"] = env["VPR_DATA_SOURCE_MODE"]
        for source in payload["sources"].values():
            source["mode"] = env["VPR_DATA_SOURCE_MODE"]

    for name in DEFAULT_SOURCE_NAMES:
        prefix = f"VPR_{name.upper()}_"
        source = payload["sources"].setdefault(name, {"name": name})
        if env.get(f"{prefix}MODE"):
            source["mode"] = env[f"{prefix}MODE"]
        if env.get(f"{prefix}LOCAL_FILE"):
            source["local_file"] = env[f"{prefix}LOCAL_FILE"]
        if env.get(f"{prefix}ONLINE_ENABLED"):
            source["online_enabled"] = env[f"{prefix}ONLINE_ENABLED"].lower() in {"1", "true", "yes"}
        if env.get(f"{prefix}TTL_SECONDS"):
            source["ttl_seconds"] = int(env[f"{prefix}TTL_SECONDS"])
        if env.get(f"{prefix}CACHE_DIR"):
            source["cache_dir"] = env[f"{prefix}CACHE_DIR"]
        if env.get(f"{prefix}TIMEOUT_SECONDS"):
            source["timeout_seconds"] = float(env[f"{prefix}TIMEOUT_SECONDS"])
        if env.get(f"{prefix}RETRY_COUNT"):
            source["retry_count"] = int(env[f"{prefix}RETRY_COUNT"])
        if env.get(f"{prefix}RETRY_BACKOFF_SECONDS"):
            source["retry_backoff_seconds"] = float(env[f"{prefix}RETRY_BACKOFF_SECONDS"])
        if env.get(f"{prefix}USER_AGENT"):
            source["user_agent"] = env[f"{prefix}USER_AGENT"]
        if env.get(f"{prefix}EMAIL"):
            source["email"] = env[f"{prefix}EMAIL"]

    return DataSourcesConfig.model_validate(payload)


def _parse_simple_yaml_config(path: Path) -> DataSourcesConfig:
    if not path.exists():
        return default_data_sources_config()

    # This deliberately supports only the small checked-in config shape, avoiding a YAML dependency.
    current_source: str | None = None
    payload: dict[str, Any] = {"sources": {}}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not raw_line.startswith(" "):
            key, value = _split_scalar(line)
            if key == "sources":
                continue
            payload[key] = value
            current_source = None
            continue
        stripped = line.strip()
        if raw_line.startswith("  ") and not raw_line.startswith("    ") and stripped.endswith(":"):
            current_source = stripped[:-1]
            payload["sources"][current_source] = {"name": current_source}
            continue
        if current_source and raw_line.startswith("    "):
            key, value = _split_scalar(stripped)
            payload["sources"][current_source][key] = value

    return DataSourcesConfig.model_validate(payload)


def _split_scalar(line: str) -> tuple[str, Any]:
    key, raw_value = line.split(":", 1)
    value = raw_value.strip()
    if value.lower() in {"true", "false"}:
        return key.strip(), value.lower() == "true"
    if value.lower() in {"null", "none", ""}:
        return key.strip(), None
    if value.isdigit():
        return key.strip(), int(value)
    return key.strip(), value.strip('"')
