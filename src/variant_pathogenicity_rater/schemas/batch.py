from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from variant_pathogenicity_rater.schemas.classification import ClassificationResult
from variant_pathogenicity_rater.schemas.common import SchemaModel


class BatchRecordError(SchemaModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class FailedBatchRecord(SchemaModel):
    input_index: int = Field(..., ge=0)
    input_record_hash: str = Field(..., min_length=1)
    raw_record: dict[str, Any] | str | None = None
    error: BatchRecordError


class BatchVariantResult(SchemaModel):
    input_index: int = Field(..., ge=0)
    input_record_hash: str = Field(..., min_length=1)
    normalized_variant_key: str | None = None
    status: Literal["ok", "error"] = "ok"
    classification_result: ClassificationResult | dict[str, Any] | None = None
    error: BatchRecordError | None = None
    review_required: bool = True
    review_flags: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    annotation_provenance: list[dict[str, Any]] = Field(default_factory=list)
    normalization_identity: dict[str, Any] | None = None
    transcript_selection_summary: dict[str, Any] | None = None
    context_consistency_summary: dict[str, Any] | None = None


class BatchSummary(SchemaModel):
    total_records: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    classification_distribution: dict[str, int] = Field(default_factory=dict)
    review_required_count: int = Field(..., ge=0)
    conflict_count: int = Field(..., ge=0)
    failed_records_summary: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_warnings: list[str] = Field(default_factory=list)


class BatchResult(SchemaModel):
    batch_id: str = Field(..., min_length=1)
    total_records: int = Field(..., ge=0)
    succeeded: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    summary: BatchSummary
    results: list[BatchVariantResult] = Field(default_factory=list)
    failed_records: list[FailedBatchRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    started_at: str = Field(..., min_length=1)
    completed_at: str = Field(..., min_length=1)
