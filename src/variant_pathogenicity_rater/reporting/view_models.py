from __future__ import annotations

from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.schemas.report import EvidenceReportEntry, VariantReportSummary


class VariantReportView(SchemaModel):
    gene: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    coordinate: str | None = None
    consequence: str | None = None
    resolution_status: str | None = None


class EvidenceReportView(SchemaModel):
    evidence_id: str | None = None
    code: str | None = None
    strength: str | None = None
    direction: str | None = None
    display_status: str = "unknown"
    reason: str = ""
    source_name: str | None = None
    review_required: bool = True


class EvidenceReportEntryView(SchemaModel):
    entry: EvidenceReportEntry
    display_status: str = "unknown"
    review_status_label: str | None = None
    counted_by_classifier: bool = False
    is_manual_reviewed: bool = False
    is_external_source: bool = False
    is_clingen_erepo: bool = False


class EvidenceSectionsView(SchemaModel):
    counted: list[EvidenceReportEntryView] = Field(default_factory=list)
    review_note: list[EvidenceReportEntryView] = Field(default_factory=list)
    manual_reviewed: list[EvidenceReportEntryView] = Field(default_factory=list)
    external_source: list[EvidenceReportEntryView] = Field(default_factory=list)
    clingen_erepo: list[EvidenceReportEntryView] = Field(default_factory=list)


class ProviderReportView(SchemaModel):
    provider_name: str
    requested_mode: str = "default"
    configured_mode: str | None = None
    outcome: str = "skipped"
    records_count: int = 0
    limitations: list[str] = Field(default_factory=list)


class ClassificationReportView(SchemaModel):
    final_classification: str
    confidence: float
    combination_rule: str | None = None
    human_review_required: bool = True


class ReviewReportView(SchemaModel):
    review_flags: list[Any] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ReportViewModel(SchemaModel):
    variant: VariantReportView
    context: dict[str, Any] = Field(default_factory=dict)
    providers: list[ProviderReportView] = Field(default_factory=list)
    evidence: list[EvidenceReportView] = Field(default_factory=list)
    evidence_sections: EvidenceSectionsView = Field(default_factory=EvidenceSectionsView)
    classification: ClassificationReportView
    review: ReviewReportView
    summary: VariantReportSummary
    audit_trail: list[Any] = Field(default_factory=list)
    has_computational_evidence: bool = False
    has_spliceai_evidence: bool = False
