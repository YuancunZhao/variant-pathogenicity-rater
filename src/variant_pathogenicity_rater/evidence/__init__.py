"""Evidence source adapters and normalization helpers."""

from variant_pathogenicity_rater.evidence.population import MockPopulationFrequencyProvider
from variant_pathogenicity_rater.evidence.status import (
    EvidenceDisplayStatus,
    EvidenceStatusView,
    EvidenceWorkflowStatus,
    build_evidence_status_view,
    is_applied_evidence,
    is_candidate_evidence,
    is_combiner_eligible,
    is_review_note_evidence,
    split_evidence_by_status,
    summarize_evidence_status,
)
from variant_pathogenicity_rater.evidence.literature import (
    LiteratureProvider,
    LiteratureQuery,
    LiteratureQueryResult,
    MockLiteratureProvider,
    extract_literature_evidence,
    map_literature_claim_to_candidate_evidence,
    parse_literature_record,
)

__all__ = ["MockPopulationFrequencyProvider"]

from variant_pathogenicity_rater.evidence.clinvar import (
    ClinVarProvider,
    ClinVarQuery,
    ClinVarQueryResult,
    MockClinVarProvider,
    map_clinvar_record_to_candidate_evidence,
    parse_clinvar_record,
)
from variant_pathogenicity_rater.evidence.population import MockPopulationFrequencyProvider

__all__ = [
    "ClinVarProvider",
    "ClinVarQuery",
    "ClinVarQueryResult",
    "MockClinVarProvider",
    "LiteratureProvider",
    "LiteratureQuery",
    "LiteratureQueryResult",
    "MockLiteratureProvider",
    "MockPopulationFrequencyProvider",
    "EvidenceDisplayStatus",
    "EvidenceStatusView",
    "EvidenceWorkflowStatus",
    "build_evidence_status_view",
    "is_applied_evidence",
    "is_candidate_evidence",
    "is_combiner_eligible",
    "is_review_note_evidence",
    "split_evidence_by_status",
    "summarize_evidence_status",
    "extract_literature_evidence",
    "map_literature_claim_to_candidate_evidence",
    "map_clinvar_record_to_candidate_evidence",
    "parse_literature_record",
    "parse_clinvar_record",
]
