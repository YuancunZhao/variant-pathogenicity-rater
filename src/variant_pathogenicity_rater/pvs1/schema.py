from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


PVS1Strength = Literal[
    "PVS1",
    "PVS1_Strong",
    "PVS1_Moderate",
    "PVS1_Supporting",
    "PVS1_candidate",
    "not_applicable",
]


class PVS1Config(SchemaModel):
    enable_online_resolvers: bool = False
    cache_dir: str | None = None
    allow_start_loss_applied: bool = False
    allow_rna_supported_splice: bool = False
    max_applied_strength_when_nmd_unknown: str = "PVS1_Supporting"


class ConsequenceAssessment(SchemaModel):
    primary_consequence: str | None = None
    consequence_terms: list[str] = Field(default_factory=list)
    is_lof: bool = False
    is_splice: bool = False
    is_candidate_only_type: bool = False
    rescue_risk: bool = False
    splice_uncertainty: bool = False
    detection_sources: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class LoFMechanismAssessment(SchemaModel):
    status: Literal["known", "not_known", "unknown", "context_dependent"]
    lof_is_known: bool | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    source: str = "unknown"
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TranscriptRelevanceAssessment(SchemaModel):
    relevant: bool | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    transcript: str | None = None
    source: str = "unknown"
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class NMDPrediction(SchemaModel):
    nmd_likely: bool | None = None
    terminal_region_risk: bool = False
    exon_position_known: bool = False
    exon_number: int | None = None
    total_exons: int | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    source: str = "unknown"
    limitations: list[str] = Field(default_factory=list)


class SplicePVS1Assessment(SchemaModel):
    applicable: bool = False
    predicted_effect: str | None = None
    frameshift_after_splice: bool | None = None
    inframe_or_rescue_possible: bool | None = None
    rna_evidence: bool = False
    suggested_strength: PVS1Strength = "PVS1_candidate"
    candidate_only: bool = True
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    path: list[str] = Field(default_factory=list)


class PVS1Decision(SchemaModel):
    recommended_code: str = "not_applicable"
    strength: PVS1Strength = "not_applicable"
    applied: bool = False
    candidate_only: bool = True
    decision_path: list[str] = Field(default_factory=list)
    downgrade_reasons: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    consequence: ConsequenceAssessment | None = None
    lof_mechanism: LoFMechanismAssessment | None = None
    transcript_relevance: TranscriptRelevanceAssessment | None = None
    nmd: NMDPrediction | None = None
    splice: SplicePVS1Assessment | None = None
