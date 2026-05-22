from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceSource


class ProvenanceMetadata(SchemaModel):
    data_source: str = Field(..., min_length=1)
    source_version: str | None = None
    query: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_record_hash: str = Field(..., min_length=1)
    parser_version: str = Field(default="v1", min_length=1)
    source_url: str | None = None
    endpoint: str | None = None
    review_status: str | None = None
    last_evaluated: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)
    ancestry: str | None = None
    population: str | None = None
    allele_number: int | None = Field(default=None, ge=0)
    coverage_quality: str | None = None
    limitations: list[str] = Field(default_factory=list)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def raw_record_hash(raw_record: Any) -> str:
    return hashlib.sha256(canonical_json(raw_record).encode("utf-8")).hexdigest()


def provenance_from_raw_record(
    *,
    data_source: str,
    source_version: str | None,
    query: dict[str, Any],
    raw_record: Any,
    parser_version: str = "v1",
    confidence: float = 0.5,
    limitations: list[str] | None = None,
    retrieved_at: str | None = None,
    source_url: str | None = None,
    endpoint: str | None = None,
    review_status: str | None = None,
    last_evaluated: str | None = None,
    ancestry: str | None = None,
    population: str | None = None,
    allele_number: int | None = None,
    coverage_quality: str | None = None,
) -> ProvenanceMetadata:
    return ProvenanceMetadata(
        data_source=data_source,
        source_version=source_version,
        query=query,
        retrieved_at=retrieved_at or datetime.now(timezone.utc).isoformat(),
        raw_record_hash=raw_record_hash(raw_record),
        parser_version=parser_version,
        source_url=source_url,
        endpoint=endpoint,
        review_status=review_status,
        last_evaluated=last_evaluated,
        confidence=confidence,
        ancestry=ancestry,
        population=population,
        allele_number=allele_number,
        coverage_quality=coverage_quality,
        limitations=limitations or [],
    )


def attach_provenance_to_source(
    source: EvidenceSource,
    provenance: ProvenanceMetadata,
) -> EvidenceSource:
    source.name = provenance.data_source
    source.version = provenance.source_version
    source.retrieval_timestamp = provenance.retrieved_at
    source.query = provenance.query
    source.raw_snapshot_ref = provenance.raw_record_hash
    source.provenance = provenance
    return source
