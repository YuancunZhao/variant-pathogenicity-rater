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
