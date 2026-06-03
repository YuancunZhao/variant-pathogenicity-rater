from __future__ import annotations

from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel


class LiteratureEvidenceExtraction(SchemaModel):
    matched_variant: str | None = None
    matched_gene: str | None = None
    matched_transcript: str | None = None
    matched_disease: str | None = None
    extracted_sentences: list[str] = Field(default_factory=list)
    extraction_method: str = "structured_record"
    extraction_confidence: float = Field(default=0.5, ge=0, le=1)
    possible_acmg_codes: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)


class LiteratureEvidenceAssessment(SchemaModel):
    candidate_code: str
    suggested_strength: str = "none"
    evidence_type: str
    variant_match_level: str | None = None
    disease_match_level: str | None = None
    phenotype_match_level: str | None = None
    assay_validity: str | None = None
    case_count: int | None = Field(default=None, ge=0)
    segregation_count: int | None = Field(default=None, ge=0)
    de_novo_status: str | None = None
    trans_cis_status: str | None = None
    inheritance_context: str | None = None
    extracted_claims: list[str] = Field(default_factory=list)
    citation: str | None = None
    pmid: str | None = None
    doi: str | None = None
    source: str | None = None
    confidence: float = Field(default=0.3, ge=0, le=1)
    requires_manual_review: bool = True
    reason_not_applied: str = (
        "Suggested literature evidence is not automatically applied to ACMG classification."
    )
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_candidate_only(self) -> bool:
        return self.candidate_code.endswith("_candidate") or self.suggested_strength == "none"


class LiteratureAgentInput(SchemaModel):
    gene: str
    variant: str
    transcript: str | None = None
    disease: str | None = None
    inheritance: str | None = None
    phenotype: str | list[str] | None = None
    literature_records: list[dict[str, Any]] = Field(default_factory=list)
    pmids: list[str] = Field(default_factory=list)
    search_query: str | None = None
    use_online_search: bool = False


class LiteratureAgentResult(SchemaModel):
    literature_evidence_assessments: list[LiteratureEvidenceAssessment] = Field(
        default_factory=list
    )
    suggested_evidence: list[dict[str, Any]] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class LiteratureSearchInput(SchemaModel):
    gene: str
    variant: str
    transcript: str | None = None
    disease: str | None = None
    inheritance: str | None = None
    phenotype: str | list[str] | None = None
    criteria: list[str] = Field(default_factory=list)
    literature_records: list[dict[str, Any]] = Field(default_factory=list)
    pmids: list[str] = Field(default_factory=list)
    search_query: str | None = None
    variant_aliases: list[str] = Field(default_factory=list)
    use_online_pubmed: bool = False
    use_online_litvar: bool = False
    use_online_search: bool = False
    provider_cache_dir: str | None = None


class LiteratureSearchQuery(SchemaModel):
    source: str
    query: str
    criterion: str | None = None
    query_type: str = "keyword"
    aliases_used: list[str] = Field(default_factory=list)


class LiteratureRecord(SchemaModel):
    record_id: str
    pmid: str | None = None
    doi: str | None = None
    title: str
    abstract: str | None = None
    full_text_excerpt: str | None = None
    source: str = "caller_supplied_literature_record"
    retrieval_timestamp: str | None = None
    query: str | dict[str, Any] | None = None
    matched_gene: str | None = None
    matched_variant: str | None = None
    matched_disease: str | None = None
    matched_transcript: str | None = None
    variant_match_level: str | None = None
    disease_match_level: str | None = None
    study_id: str | None = None
    duplicate_study_group: str | None = None
    study_type: str | None = None
    evidence_domains: list[str] = Field(default_factory=list)
    extracted_claims: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    raw_record: dict[str, Any] = Field(default_factory=dict)


class LiteratureRecordNormalizationResult(SchemaModel):
    records: list[LiteratureRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[dict[str, Any]] = Field(default_factory=list)


class DuplicateGroup(SchemaModel):
    group_id: str
    reason: str
    kept_record_id: str
    duplicate_record_ids: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class LiteratureDeduplicationResult(SchemaModel):
    records: list[LiteratureRecord] = Field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)


class CriterionSummary(SchemaModel):
    criterion: str
    evidence_domain: str
    summary: str
    supporting_records: list[str] = Field(default_factory=list)
    extracted_claims: list[str] = Field(default_factory=list)
    suggested_code: str | None = None
    suggested_strength: str = "none"
    confidence: float = Field(default=0.3, ge=0, le=1)
    requires_manual_review: bool = True
    review_questions: list[str] = Field(default_factory=list)
    blocking_flags: list[dict[str, Any]] = Field(default_factory=list)
    review_flags: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class LiteratureSearchResult(SchemaModel):
    status: str = "ok"
    tool: str = "search_and_summarize_literature"
    stage: str = "general_literature_search_and_summary"
    literature_search_results: list[LiteratureRecord] = Field(default_factory=list)
    literature_summary: str = ""
    criterion_summaries: list[CriterionSummary] = Field(default_factory=list)
    literature_evidence_assessments: list[LiteratureEvidenceAssessment] = Field(
        default_factory=list
    )
    suggested_evidence: list[dict[str, Any]] = Field(default_factory=list)
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    blocking_flags: list[dict[str, Any]] = Field(default_factory=list)
    review_flags: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reviewed_evidence_drafts: list[dict[str, Any]] = Field(default_factory=list)
    reviewed_evidence: list[dict[str, Any]] = Field(default_factory=list)
    query_plan: list[LiteratureSearchQuery] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    applied_evidence: list[dict[str, Any]] = Field(default_factory=list)
    final_classification_changed: bool = False
    human_review: dict[str, Any] = Field(
        default_factory=lambda: {
            "required": True,
            "notice": "Literature search output is suggested evidence only and is not automatically applied.",
        }
    )
