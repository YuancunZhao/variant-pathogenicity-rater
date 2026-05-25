from __future__ import annotations

from dataclasses import dataclass

from variant_pathogenicity_rater.schemas.report import ReportMode


HUMAN_REVIEW_NOTE = (
    "This report is machine-generated and is not a final clinical assertion. "
    "A qualified human reviewer must verify the variant, evidence, ACMG criteria, "
    "limitations, and final classification before clinical or laboratory use."
)

VUS_NOTE = (
    "The available evidence is insufficient to support a pathogenic or benign "
    "classification. The variant should be treated as a Variant of Uncertain "
    "Significance unless and until additional reviewed evidence becomes available."
)

COMPUTATIONAL_CAUTION = (
    "Computational evidence is supporting evidence only and must not be treated "
    "as determinative without independent clinical, functional, segregation, or "
    "population evidence as applicable."
)

SPLICEAI_CAUTION = (
    "SpliceAI is computational splice prediction only. It is not functional "
    "evidence and does not by itself apply PS3, BS3, or PVS1."
)

CLINVAR_CONFLICT_ALERT = (
    "ClinVar conflict detected: conflicting external assertions require prominent "
    "manual review and should not be resolved by this report alone."
)

CANDIDATE_EVIDENCE_CAUTION = (
    "Candidate/review-note evidence is listed for manual evaluation only. It was "
    "not counted by the classification combiner unless it also appears under "
    "Applied ACMG Evidence."
)

ZH_PLACEHOLDER = (
    "Chinese report output is reserved for a future complete localization pass. "
    "This response currently preserves the English report text."
)


@dataclass(frozen=True)
class ModeTemplate:
    title: str
    include_audit_details: bool
    include_evidence_table: bool
    include_reviewer_checklist: bool
    opening_label: str


MODE_TEMPLATES: dict[ReportMode, ModeTemplate] = {
    ReportMode.CONCISE: ModeTemplate(
        title="Variant Pathogenicity Report",
        include_audit_details=False,
        include_evidence_table=False,
        include_reviewer_checklist=False,
        opening_label="Concise machine-generated ACMG report",
    ),
    ReportMode.DETAILED: ModeTemplate(
        title="Detailed Variant Pathogenicity Report",
        include_audit_details=True,
        include_evidence_table=True,
        include_reviewer_checklist=True,
        opening_label="Detailed machine-generated ACMG report",
    ),
    ReportMode.LABORATORY: ModeTemplate(
        title="Laboratory Variant Pathogenicity Report",
        include_audit_details=True,
        include_evidence_table=True,
        include_reviewer_checklist=True,
        opening_label="Laboratory-facing machine-generated ACMG report",
    ),
    ReportMode.CLINICIAN: ModeTemplate(
        title="Clinician Variant Pathogenicity Report",
        include_audit_details=False,
        include_evidence_table=False,
        include_reviewer_checklist=True,
        opening_label="Clinician-facing machine-generated ACMG report",
    ),
}
