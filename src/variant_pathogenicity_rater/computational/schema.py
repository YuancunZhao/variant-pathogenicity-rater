from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceDirection, EvidenceStrength


class PredictorGroup(StrEnum):
    MISSENSE = "missense"
    SPLICE = "splice"
    CONSERVATION = "conservation"
    META = "meta"
    UNKNOWN = "unknown"


class PredictorDirection(StrEnum):
    PATHOGENIC = "pathogenic"
    BENIGN = "benign"
    NEUTRAL = "neutral"
    AMBIGUOUS = "ambiguous"


class PredictorCall(SchemaModel):
    method: str = Field(..., min_length=1)
    group: PredictorGroup = PredictorGroup.UNKNOWN
    direction: PredictorDirection = PredictorDirection.NEUTRAL
    score: float | None = None
    prediction: str | None = None
    threshold: float | None = None
    transcript: str | None = None
    protein_change: str | None = None
    hgvs_p: str | None = None
    source_name: str | None = None
    source_version: str | None = None
    genome_build: str | None = None
    calibrated: bool = True
    candidate_only: bool = False
    reason: str = Field(..., min_length=1)
    limitations: list[str] = Field(default_factory=list)
    provenance: Any | None = None


class PredictorConsensus(SchemaModel):
    group: PredictorGroup
    consensus_direction: PredictorDirection = PredictorDirection.NEUTRAL
    applied_eligible: bool = False
    candidate_only: bool = False
    support_count: int = 0
    opposing_count: int = 0
    neutral_count: int = 0
    ambiguous_count: int = 0
    available_predictor_count: int = 0
    required_support_count: int = 2
    predictor_summary: list[dict[str, Any]] = Field(default_factory=list)
    conflict_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)


class ComputationalEvidenceDecision(SchemaModel):
    recommended_code: str | None = None
    strength: EvidenceStrength = EvidenceStrength.NONE
    direction: EvidenceDirection = EvidenceDirection.NEUTRAL
    applied: bool = False
    candidate_only: bool = False
    predictor_summary: list[dict[str, Any]] = Field(default_factory=list)
    predictor_groups: dict[str, Any] = Field(default_factory=dict)
    consensus_direction: PredictorDirection = PredictorDirection.NEUTRAL
    thresholds_used: dict[str, Any] = Field(default_factory=dict)
    quality_checks: list[dict[str, Any]] = Field(default_factory=list)
    conflict_reasons: list[str] = Field(default_factory=list)
    double_counting_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    requires_review: bool = True

