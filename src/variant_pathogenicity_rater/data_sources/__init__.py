from __future__ import annotations

from typing import Any

__all__ = [
    "CacheEntry",
    "DataSourceConfig",
    "DataSourcesConfig",
    "DiskCache",
    "ProviderMode",
    "ProvenanceMetadata",
    "attach_provenance_to_source",
    "load_data_sources_config",
    "provenance_from_raw_record",
]


def __getattr__(name: str) -> Any:
    if name in {"CacheEntry", "DiskCache"}:
        from variant_pathogenicity_rater.data_sources.cache import CacheEntry, DiskCache

        return {"CacheEntry": CacheEntry, "DiskCache": DiskCache}[name]
    if name in {
        "DataSourceConfig",
        "DataSourcesConfig",
        "ProviderMode",
        "load_data_sources_config",
    }:
        from variant_pathogenicity_rater.data_sources.config import (
            DataSourceConfig,
            DataSourcesConfig,
            ProviderMode,
            load_data_sources_config,
        )

        return {
            "DataSourceConfig": DataSourceConfig,
            "DataSourcesConfig": DataSourcesConfig,
            "ProviderMode": ProviderMode,
            "load_data_sources_config": load_data_sources_config,
        }[name]
    if name in {
        "ProvenanceMetadata",
        "attach_provenance_to_source",
        "provenance_from_raw_record",
    }:
        from variant_pathogenicity_rater.data_sources.provenance import (
            ProvenanceMetadata,
            attach_provenance_to_source,
            provenance_from_raw_record,
        )

        return {
            "ProvenanceMetadata": ProvenanceMetadata,
            "attach_provenance_to_source": attach_provenance_to_source,
            "provenance_from_raw_record": provenance_from_raw_record,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
