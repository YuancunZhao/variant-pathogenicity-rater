from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


class ClinGenERepoMatchLevel(StrEnum):
    EXACT_VARIANT = "exact_variant"
    SAME_GENE = "same_gene"
    SAME_PROTEIN = "same_protein"
    NO_MATCH = "no_match"


class ERepoEvidenceSummary(SchemaModel):
    summary_id: str | None = None
    evidence_type: str | None = None
    summary_text: str = Field(..., min_length=1)
    direction: str | None = None
    criteria_codes: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class ERepoCriteriaSummary(SchemaModel):
    criterion: str = Field(..., min_length=1)
    strength: str | None = None
    direction: str | None = None
    applied_by_vcep: bool = True
    summary: str | None = None
    citations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClinGenERepoRecord(SchemaModel):
    record_id: str = Field(..., min_length=1)
    gene: str | None = None
    variant_identifiers: dict[str, Any] = Field(default_factory=dict)
    ca_id: str | None = None
    clinvar_variation_id: str | None = None
    rsid: str | None = None
    hgvs_g: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    genomic_key: str | None = None
    transcript: str | None = None
    protein_change: str | None = None
    disease_condition: str | None = None
    disease_id: str | None = None
    inheritance: str | None = None
    vcep_name: str | None = None
    affiliation_id: str | None = None
    classification: str = Field(..., min_length=1)
    classification_date: date | None = None
    classification_version: str | None = None
    criteria_applied: list[ERepoCriteriaSummary] = Field(default_factory=list)
    evidence_summaries: list[ERepoEvidenceSummary] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    source_url: str | None = None
    api_endpoint: str | None = None
    raw_snapshot_hash: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class ClinGenERepoMatch(SchemaModel):
    query_variant: dict[str, Any] = Field(default_factory=dict)
    record: ClinGenERepoRecord
    match_level: ClinGenERepoMatchLevel
    confidence: float = Field(..., ge=0, le=1)
    matched_identifiers: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    condition_match: bool | None = None
    transcript_match: bool | None = None
    gene_match: bool | None = None
    protein_only_match: bool = False
    authoritative_review_note: bool = True
    automatic_acmg_application: bool = False


class VCEPSignal(SchemaModel):
    gene: str = Field(..., min_length=1)
    disease_condition: str | None = None
    vcep_name: str | None = None
    activity_status: str = "curation_activity_observed"
    record_count: int = Field(default=0, ge=0)
    source_records: list[str] = Field(default_factory=list)
    signal_type: str = "gene_level_vcep_activity"
    limitations: list[str] = Field(default_factory=list)


class ERepoReviewedEvidenceDraft(SchemaModel):
    source_erepo_record_id: str = Field(..., min_length=1)
    source_candidate_evidence_id: str | None = None
    suggested_acmg_code: str | None = None
    suggested_strength: str | None = None
    suggested_direction: str | None = None
    evidence_status: str = "needs_more_info"
    curator_decision: str = "Review ClinGen ERepo curated assertion before applying evidence."
    rationale: str = Field(..., min_length=1)
    citation: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    review_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
