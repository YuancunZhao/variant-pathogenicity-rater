from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag, SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem
from variant_pathogenicity_rater.schemas.variant import Variant


class ACMGClassification(StrEnum):
    PATHOGENIC = "pathogenic"
    LIKELY_PATHOGENIC = "likely_pathogenic"
    UNCERTAIN_SIGNIFICANCE = "vus"
    LIKELY_BENIGN = "likely_benign"
    BENIGN = "benign"


class ClassificationResult(SchemaModel):
    result_id: str = Field(..., min_length=1)
    variant: Variant
    final_classification: ACMGClassification
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    applied_combination_rule: str | None = None
    pathogenic_evidence_summary: list[str] = Field(default_factory=list)
    benign_evidence_summary: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0, le=1)
    human_review_required: bool = True
    report_text: str = Field(..., min_length=1)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    audit_trail: list[AuditTrail] = Field(default_factory=list)
