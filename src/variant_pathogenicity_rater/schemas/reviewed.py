from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import AuditTrail, SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceDirection, EvidenceStrength


class ReviewedEvidenceStatus(StrEnum):
    REVIEWED_APPLIED = "reviewed_applied"
    REVIEWED_REJECTED = "reviewed_rejected"
    NEEDS_MORE_INFO = "needs_more_info"


class ReviewedEvidence(SchemaModel):
    source_candidate_evidence_id: str | None = None
    acmg_code: EvidenceCode
    strength: EvidenceStrength
    direction: EvidenceDirection
    curator_decision: str = Field(..., min_length=1)
    curator_name: str | None = None
    review_date: date
    rationale: str = Field(..., min_length=1)
    citation: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    override_reason: str | None = None
    evidence_status: ReviewedEvidenceStatus
    audit_trail: list[AuditTrail] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reviewed_application(self) -> "ReviewedEvidence":
        if self.evidence_status != ReviewedEvidenceStatus.REVIEWED_APPLIED:
            return self
        if not (self.citation or self.provenance):
            raise ValueError("reviewed_applied evidence requires citation or provenance.")
        if self.strength == EvidenceStrength.NONE:
            raise ValueError("reviewed_applied evidence cannot use strength=none.")
        if self.direction in {EvidenceDirection.NEUTRAL, EvidenceDirection.CONFLICTING}:
            raise ValueError("reviewed_applied evidence requires pathogenic or benign direction.")
        return self


class ReviewedEvidenceResult(SchemaModel):
    applied_items: list[Any] = Field(default_factory=list)
    review_note_items: list[Any] = Field(default_factory=list)
    review_flags: list[Any] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reviewed_evidence_records: list[dict[str, Any]] = Field(default_factory=list)
