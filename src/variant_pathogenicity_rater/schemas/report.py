from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection
from variant_pathogenicity_rater.schemas.classification import ClassificationResult
from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency


class ReportFormat(StrEnum):
    MARKDOWN = "markdown"
    PLAIN_TEXT = "plain_text"
    JSON = "json"


class ReportMode(StrEnum):
    CONCISE = "concise"
    DETAILED = "detailed"
    LABORATORY = "laboratory"
    CLINICIAN = "clinician"


class ReportLanguage(StrEnum):
    ENGLISH = "en"
    CHINESE = "zh"


class DataSourceSummary(SchemaModel):
    name: str = Field(..., min_length=1)
    version: str | None = None
    retrieval_timestamp: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    query: dict[str, Any] = Field(default_factory=dict)
    raw_snapshot_ref: str | None = None


class EvidenceReportEntry(SchemaModel):
    evidence_id: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)
    strength: str = Field(..., min_length=1)
    direction: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0, le=1)
    requires_review: bool = True
    triggered_by: list[str] = Field(default_factory=list)
    citation: str | None = None
    provenance: Any | None = None
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    pvs1_decision_path: list[str] = Field(default_factory=list)
    pvs1_downgrade_reasons: list[str] = Field(default_factory=list)
    pvs1_blocking_reasons: list[str] = Field(default_factory=list)
    population_decision_path: list[str] = Field(default_factory=list)
    population_thresholds: dict[str, Any] = Field(default_factory=dict)
    population_quality_checks: list[dict[str, Any]] = Field(default_factory=list)
    population_blocking_reasons: list[str] = Field(default_factory=list)
    computational_predictor_summary: list[dict[str, Any]] = Field(default_factory=list)
    computational_thresholds: dict[str, Any] = Field(default_factory=dict)
    computational_quality_checks: list[dict[str, Any]] = Field(default_factory=list)
    computational_conflict_reasons: list[str] = Field(default_factory=list)
    computational_consensus_direction: str | None = None
    ps1_pm5_decision_path: list[str] = Field(default_factory=list)
    ps1_pm5_quality_checks: list[dict[str, Any]] = Field(default_factory=list)
    ps1_pm5_blocking_reasons: list[str] = Field(default_factory=list)
    ps1_pm5_downgrade_reasons: list[str] = Field(default_factory=list)
    ps1_pm5_review_note: str | None = None
    curator_decision: str | None = None
    curator_name: str | None = None
    review_date: str | None = None
    override_reason: str | None = None
    source_candidate_evidence_id: str | None = None
    reviewed_evidence_status: str | None = None
    reviewed_provenance: Any | None = None
    clingen_erepo_match: dict[str, Any] | None = None
    clingen_erepo_record: dict[str, Any] | None = None
    clingen_erepo_criteria: list[dict[str, Any]] = Field(default_factory=list)
    clingen_erepo_summaries: list[dict[str, Any]] = Field(default_factory=list)
    vcep_override: dict[str, Any] | None = None


class VariantReportSummary(SchemaModel):
    variant_id: str = Field(..., min_length=1)
    gene_symbol: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    genomic_location: str = Field(..., min_length=1)
    final_classification: str = Field(..., min_length=1)
    classification_label: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0, le=1)
    applied_combination_rule: str | None = None
    triggered_acmg_evidence: list[EvidenceReportEntry] = Field(default_factory=list)
    candidate_acmg_evidence: list[EvidenceReportEntry] = Field(default_factory=list)
    pathogenic_evidence_summary: list[str] = Field(default_factory=list)
    benign_evidence_summary: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    clinvar_conflict_detected: bool = False
    limitations: list[str] = Field(default_factory=list)
    human_review_note: str = Field(..., min_length=1)
    data_source_summary: list[DataSourceSummary] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    transcript_selection: TranscriptSelection | None = None
    context_consistency: ContextConsistency | None = None
    vcep_profile_context: dict[str, Any] | None = None


class VariantReport(SchemaModel):
    report_id: str = Field(..., min_length=1)
    result_id: str = Field(..., min_length=1)
    mode: ReportMode
    output_format: ReportFormat
    language: ReportLanguage = ReportLanguage.ENGLISH
    summary: VariantReportSummary
    content: str | dict[str, Any]
    source_result: ClassificationResult
    human_review_required: bool = True
