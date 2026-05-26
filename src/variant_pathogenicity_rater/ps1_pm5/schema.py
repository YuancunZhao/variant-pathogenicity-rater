from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceDirection, EvidenceStrength


class ParsedProteinChange(SchemaModel):
    accession: str | None = None
    raw: str | None = None
    ref_aa: str | None = None
    position: int | None = Field(default=None, ge=1)
    alt_aa: str | None = None
    change_type: str = "unknown"
    parseable: bool = False
    limitations: list[str] = Field(default_factory=list)


class AminoAcidMatch(SchemaModel):
    query_protein_accession: str | None = None
    comparator_protein_accession: str | None = None
    query_transcript: str | None = None
    comparator_transcript: str | None = None
    query_hgvs_p: str | None = None
    comparator_hgvs_p: str | None = None
    query_parsed: ParsedProteinChange | None = None
    comparator_parsed: ParsedProteinChange | None = None
    ref_aa: str | None = None
    position: int | None = Field(default=None, ge=1)
    alt_aa: str | None = None
    change_type: str = "unknown"
    protein_parseable: bool = False
    same_residue: bool = False
    same_amino_acid_change: bool = False
    different_missense_change: bool = False
    transcript_or_protein_match: bool = False
    confidence: Literal["high", "moderate", "low", "unavailable"] = "unavailable"
    limitations: list[str] = Field(default_factory=list)


class ClinVarComparison(SchemaModel):
    variation_id: str | None = None
    clinical_significance: str | None = None
    review_status: str | None = None
    review_stars: int | None = None
    submitter_count: int | None = None
    conflict_status: str | None = None
    germline_or_somatic: str | None = None
    citations: list[str] = Field(default_factory=list)
    is_pathogenic_or_likely_pathogenic: bool = False
    has_conflict: bool = False
    is_germline_applicable: bool = True
    high_quality_for_applied: bool = False
    low_quality_candidate_only: bool = False
    same_nucleotide_change: bool = False
    different_nucleotide_change: bool = False
    query_hgvs_c: str | None = None
    comparator_hgvs_c: str | None = None
    query_genomic_key: str | None = None
    comparator_genomic_key: str | None = None
    source_snapshot: str | None = None
    source_version: str | None = None
    raw_snapshot_ref: str | None = None


class ConditionMatch(SchemaModel):
    query_condition: str | None = None
    comparator_conditions: list[str] = Field(default_factory=list)
    matched: bool = False
    match_type: Literal[
        "exact",
        "normalized_overlap",
        "ontology_id",
        "missing",
        "mismatch",
        "ambiguous",
    ] = "missing"
    blocking: bool = True
    matched_terms: list[str] = Field(default_factory=list)
    unmatched_terms: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class PS1PM5EvidenceGeneration(SchemaModel):
    status: Literal["applied", "candidate", "blocked", "unavailable"] = "unavailable"
    candidate_only: bool = True
    automatic_application: bool = False
    criterion_rationale: str = ""
    review_note: str = ""
    decision_path: list[str] = Field(default_factory=list)
    source_record_count: int = 0
    selected_comparator_variation_id: str | None = None
    all_comparators_summary: list[dict[str, Any]] = Field(default_factory=list)


class PS1PM5Decision(SchemaModel):
    recommended_code: Literal["PS1", "PM5"] | None = None
    strength: EvidenceStrength = EvidenceStrength.NONE
    direction: EvidenceDirection = EvidenceDirection.NEUTRAL
    applied: bool = False
    candidate_only: bool = False
    requires_review: bool = True
    amino_acid_match: AminoAcidMatch
    clinvar_comparison: ClinVarComparison
    condition_match: ConditionMatch
    generation: PS1PM5EvidenceGeneration
    quality_checks: list[dict[str, Any]] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    downgrade_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
