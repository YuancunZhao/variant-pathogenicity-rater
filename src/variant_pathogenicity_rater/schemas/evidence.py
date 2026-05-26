from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag, SchemaModel


class EvidenceStrength(StrEnum):
    STAND_ALONE = "stand_alone"
    VERY_STRONG = "very_strong"
    STRONG = "strong"
    MODERATE = "moderate"
    SUPPORTING = "supporting"
    NONE = "none"


class EvidenceDirection(StrEnum):
    PATHOGENIC = "pathogenic"
    BENIGN = "benign"
    NEUTRAL = "neutral"
    CONFLICTING = "conflicting"


class LiteratureEvidenceType(StrEnum):
    FUNCTIONAL = "functional"
    DE_NOVO = "de_novo"
    SEGREGATION = "segregation"
    CASE_REPORT = "case_report"
    PHENOTYPE_SPECIFICITY = "phenotype_specificity"


class LiteratureEvidenceQuality(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"
    UNKNOWN = "unknown"


class LiteratureCandidateEvidenceType(StrEnum):
    PS3_CANDIDATE = "PS3_candidate"
    BS3_CANDIDATE = "BS3_candidate"
    PS2_CANDIDATE = "PS2_candidate"
    PM6_CANDIDATE = "PM6_candidate"
    PP1_CANDIDATE = "PP1_candidate"
    PS4_CANDIDATE = "PS4_candidate"
    PP4_CANDIDATE = "PP4_candidate"


class EvidenceSource(SchemaModel):
    name: str = Field(..., min_length=1)
    version: str | None = None
    url: str | None = None
    database_id: str | None = None
    retrieval_timestamp: str | None = None
    query: dict[str, Any] = Field(default_factory=dict)
    raw_snapshot_ref: str | None = None
    provenance: Any | None = None


class PopulationFrequency(SchemaModel):
    source: EvidenceSource | None = None
    overall_af: float | None = Field(default=None, ge=0, le=1)
    max_pop_af: float | None = Field(default=None, ge=0, le=1)
    population_name: str = Field(..., min_length=1)
    allele_count: int | None = Field(default=None, ge=0)
    allele_number: int | None = Field(default=None, ge=0)
    homozygote_count: int | None = Field(default=None, ge=0)
    hemizygote_count: int | None = Field(default=None, ge=0)
    data_source: str = Field(..., min_length=1)
    filter_status: str | None = None
    data_version: str | None = None
    is_absent: bool = False
    faf95: float | None = Field(default=None, ge=0, le=1)
    filtering_af: float | None = Field(default=None, ge=0, le=1)
    genome_build: str | None = None
    dataset_version: str | None = None
    coverage_quality: str | None = None
    population_match: bool | None = None
    limitations: list[str] = Field(default_factory=list)


class SplicePrediction(SchemaModel):
    source: EvidenceSource
    DS_AG: float | None = Field(default=None, ge=0, le=1)
    DS_AL: float | None = Field(default=None, ge=0, le=1)
    DS_DG: float | None = Field(default=None, ge=0, le=1)
    DS_DL: float | None = Field(default=None, ge=0, le=1)
    max_delta_score: float = Field(..., ge=0, le=1)
    predicted_consequence: str = Field(..., min_length=1)
    affected_gene: str = Field(..., min_length=1)
    transcript: str | None = None
    source_version: str | None = None
    genome_build: str | None = None
    provenance: Any | None = None
    candidate_only: bool = False
    limitations: list[str] = Field(default_factory=list)


class ComputationalPrediction(SchemaModel):
    source: EvidenceSource
    method: str = Field(..., min_length=1)
    score: float | None = None
    prediction: str = Field(..., min_length=1)
    threshold: float | None = None
    transcript: str | None = None
    hgvs_p: str | None = None
    protein_change: str | None = None
    genome_build: str | None = None
    candidate_only: bool = False
    limitations: list[str] = Field(default_factory=list)
    splice_prediction: SplicePrediction | None = None


class ClinVarRecord(SchemaModel):
    source: EvidenceSource
    variation_id: str | None = None
    gene_symbol: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    protein_change: str | None = None
    chromosome: str | None = None
    position: int | None = Field(default=None, ge=1)
    ref: str | None = None
    alt: str | None = None
    genome_build: str | None = None
    clinical_significance: str = Field(..., min_length=1)
    review_status: str | None = None
    review_stars: int | None = Field(default=None, ge=0, le=4)
    review_confidence: str | None = None
    condition: str | None = None
    conditions: list[str] = Field(default_factory=list)
    submitter_count: int | None = Field(default=None, ge=0)
    last_evaluated: date | None = None
    conflicting_interpretations: bool = False
    conflict_status: str | None = None
    germline_or_somatic: str | None = None
    citations: list[str] = Field(default_factory=list)


class LiteratureEvidence(SchemaModel):
    source: EvidenceSource
    article_id: str | None = None
    study_id: str | None = None
    pmid: str | None = None
    doi: str | None = None
    citation: str = Field(..., min_length=1)
    citations: list[str] = Field(default_factory=list)
    title: str = Field(..., min_length=1)
    journal: str | None = None
    year: int | None = Field(default=None, ge=1900)
    finding: str = Field(..., min_length=1)
    relevance: str | None = None
    evidence_types: list[LiteratureEvidenceType] = Field(default_factory=list)
    quality: LiteratureEvidenceQuality = LiteratureEvidenceQuality.UNKNOWN
    duplicate_study_group: str | None = None
    requires_review: bool = True
    extracted_claims: list["LiteratureClaim"] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def preserve_citation(self) -> "LiteratureEvidence":
        if not (self.citation or self.pmid or self.doi or self.citations):
            raise ValueError("Literature evidence must preserve at least one citation.")
        return self


class LiteratureClaim(SchemaModel):
    claim_id: str = Field(..., min_length=1)
    study_id: str = Field(..., min_length=1)
    evidence_type: LiteratureEvidenceType
    evidence_type_candidate: LiteratureCandidateEvidenceType | None = None
    candidate_codes: list[EvidenceCode] = Field(default_factory=list)
    direction: EvidenceDirection = EvidenceDirection.NEUTRAL
    description: str = Field(..., min_length=1)
    quality: LiteratureEvidenceQuality = LiteratureEvidenceQuality.UNKNOWN
    evidence_quality: LiteratureEvidenceQuality | None = None
    assay_type: str | None = None
    phenotype_match: bool | None = None
    condition_match: bool | None = None
    variant_match_level: str | None = None
    duplicate_study_group: str | None = None
    extraction_confidence: float = Field(default=0.5, ge=0, le=1)
    citation: str = Field(..., min_length=1)
    extracted_from: str | None = None
    requires_review: bool = True
    requires_manual_review: bool = True
    review_notes: list[str] = Field(default_factory=list)


class EvidenceItem(SchemaModel):
    evidence_id: str = Field(..., min_length=1)
    code: EvidenceCode
    strength: EvidenceStrength
    direction: EvidenceDirection
    reason: str = Field(..., min_length=1)
    source: EvidenceSource
    confidence: float = Field(..., ge=0, le=1)
    requires_review: bool = True
    candidate_only: bool | None = None
    applied: bool | None = None
    triggered_by: list[str] = Field(default_factory=list)
    supporting_data: dict[str, Any] = Field(default_factory=dict)
    audit_trail: list[AuditTrail] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)

    @model_validator(mode="after")
    def synchronize_review_note_status(self) -> "EvidenceItem":
        supporting_candidate = bool(
            self.supporting_data.get("candidate_only")
            or self.supporting_data.get("evidence_status") == "candidate"
            or self.supporting_data.get("applied") is False
        )
        if self.candidate_only is None:
            self.candidate_only = supporting_candidate
        if self.applied is None:
            self.applied = not bool(self.candidate_only) and self.strength != EvidenceStrength.NONE
        return self
