from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import Field

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.provenance import provenance_from_raw_record
from variant_pathogenicity_rater.schemas.annotation import OnlineResolutionResult
from variant_pathogenicity_rater.schemas.common import SchemaModel


class OnlineResolverConfig(SchemaModel):
    name: str = Field(..., min_length=1)
    enabled: bool = False
    online_enabled: bool = False
    source_version: str | None = None
    timeout_seconds: float = Field(default=5.0, gt=0)
    ttl_seconds: int | None = Field(default=86400, ge=0)
    cache_dir: str = ".cache/variant_pathogenicity_rater/annotation"


class OnlineResolver:
    mode = "online_resolver"

    def __init__(
        self,
        config: OnlineResolverConfig,
        *,
        fetcher: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.fetcher = fetcher
        self.cache = DiskCache(Path(config.cache_dir), ttl_seconds=config.ttl_seconds)

    def resolve(self, query: dict[str, Any]) -> OnlineResolutionResult:
        if not self.config.enabled or not self.config.online_enabled:
            return OnlineResolutionResult(
                limitations=[
                    f"{self.config.name} is disabled by default; no online request was attempted."
                ]
            )
        if self.fetcher is None:
            return OnlineResolutionResult(
                limitations=[
                    f"{self.config.name} has no online implementation configured; interpretation continued."
                ]
            )
        try:
            entry, cache_hit = self.cache.get_or_set(
                provider=self.config.name,
                mode=self.mode,
                source_version=self.config.source_version,
                query=query,
                loader=lambda: self._fetch_payload(query),
                ttl_seconds=self.config.ttl_seconds,
            )
            retrieved_at = entry.created_at
            if isinstance(entry.payload, dict):
                retrieved_at = entry.payload.get("retrieved_at") or entry.created_at
            provenance = provenance_from_raw_record(
                data_source=self.config.name,
                source_version=self.config.source_version,
                query=query,
                raw_record=entry.payload,
                parser_version="online-resolver-v1",
                retrieved_at=retrieved_at,
                confidence=0.5,
                limitations=[
                    "Online annotation result is descriptive context only and does not directly trigger ACMG evidence."
                ],
            )
            return OnlineResolutionResult(
                resolved=entry.payload,
                provenance=provenance,
                cache_hit=cache_hit,
                limitations=["Online resolver cache hit."] if cache_hit else [],
            )
        except Exception as exc:  # noqa: BLE001 - online failures must not break interpretation.
            return OnlineResolutionResult(
                limitations=[
                    f"{self.config.name} online resolver failed: {exc.__class__.__name__}: {exc}",
                    "External data failure was captured as a limitation; pipeline execution can continue.",
                ]
            )

    def _fetch_payload(self, query: dict[str, Any]) -> dict[str, Any]:
        assert self.fetcher is not None
        payload = self.fetcher(query, self.config.timeout_seconds)
        return {
            "source": self.config.name,
            "version": self.config.source_version,
            "source_version": self.config.source_version,
            "query": query,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "record": payload,
        }


class OnlineVariantNormalizer(OnlineResolver):
    def __init__(
        self,
        config: OnlineResolverConfig | None = None,
        *,
        fetcher: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            config
            or OnlineResolverConfig(
                name="online_variant_normalizer",
                source_version="placeholder-v1",
            ),
            fetcher=fetcher,
        )


class TranscriptMetadataResolver(OnlineResolver):
    def __init__(
        self,
        config: OnlineResolverConfig | None = None,
        *,
        fetcher: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            config
            or OnlineResolverConfig(
                name="transcript_metadata_resolver",
                source_version="MANE/RefSeq/Ensembl-placeholder-v1",
            ),
            fetcher=fetcher,
        )
