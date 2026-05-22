from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.data_sources.provenance import canonical_json, raw_record_hash
from variant_pathogenicity_rater.schemas.common import SchemaModel


class CacheEntry(SchemaModel):
    key: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    mode: str = Field(..., min_length=1)
    source_version: str | None = None
    query: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_seconds: int | None = Field(default=None, ge=0)
    payload: Any
    raw_record_hash: str = Field(..., min_length=1)

    def expired(self, now: datetime | None = None) -> bool:
        if self.ttl_seconds is None:
            return False
        created_at = datetime.fromisoformat(self.created_at)
        return (now or datetime.now(timezone.utc)) >= created_at + timedelta(seconds=self.ttl_seconds)


class DiskCache:
    """Small JSON disk cache for source records, keyed by provider/mode/version/query."""

    def __init__(self, root: str | Path, ttl_seconds: int | None = None) -> None:
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def cache_key(
        *,
        provider: str,
        mode: str,
        source_version: str | None,
        query: dict[str, Any],
    ) -> str:
        material = {
            "provider": provider,
            "mode": mode,
            "source_version": source_version,
            "query": query,
        }
        return raw_record_hash(material)

    def get(self, key: str) -> CacheEntry | None:
        path = self._path(key)
        if not path.exists():
            return None
        entry = CacheEntry.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if entry.expired():
            return None
        return entry

    def set(
        self,
        *,
        provider: str,
        mode: str,
        source_version: str | None,
        query: dict[str, Any],
        payload: Any,
        ttl_seconds: int | None = None,
    ) -> CacheEntry:
        key = self.cache_key(
            provider=provider,
            mode=mode,
            source_version=source_version,
            query=query,
        )
        entry = CacheEntry(
            key=key,
            provider=provider,
            mode=mode,
            source_version=source_version,
            query=query,
            ttl_seconds=self.ttl_seconds if ttl_seconds is None else ttl_seconds,
            payload=payload,
            raw_record_hash=raw_record_hash(payload),
        )
        self._path(key).write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        return entry

    def get_or_set(
        self,
        *,
        provider: str,
        mode: str,
        source_version: str | None,
        query: dict[str, Any],
        loader: Any,
        ttl_seconds: int | None = None,
    ) -> tuple[CacheEntry, bool]:
        key = self.cache_key(
            provider=provider,
            mode=mode,
            source_version=source_version,
            query=query,
        )
        cached = self.get(key)
        if cached is not None:
            return cached, True
        return (
            self.set(
                provider=provider,
                mode=mode,
                source_version=source_version,
                query=query,
                payload=loader(),
                ttl_seconds=ttl_seconds,
            ),
            False,
        )

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"
