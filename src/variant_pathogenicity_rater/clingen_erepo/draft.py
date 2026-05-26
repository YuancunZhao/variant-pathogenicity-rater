from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.clingen_erepo.schema import (
    ClinGenERepoMatch,
    ClinGenERepoMatchLevel,
    ERepoReviewedEvidenceDraft,
)


def create_erepo_reviewed_evidence_drafts(
    matches: list[ClinGenERepoMatch],
    candidate_evidence_ids: dict[str, str] | None = None,
) -> list[ERepoReviewedEvidenceDraft]:
    drafts: list[ERepoReviewedEvidenceDraft] = []
    for match in matches:
        if match.match_level != ClinGenERepoMatchLevel.EXACT_VARIANT or match.confidence < 0.8:
            continue
        record = match.record
        candidate_id = (candidate_evidence_ids or {}).get(record.record_id)
        for criterion in record.criteria_applied or []:
            drafts.append(
                ERepoReviewedEvidenceDraft(
                    source_erepo_record_id=record.record_id,
                    source_candidate_evidence_id=candidate_id,
                    suggested_acmg_code=criterion.criterion,
                    suggested_strength=criterion.strength,
                    suggested_direction=criterion.direction,
                    rationale=criterion.summary
                    or (
                        f"ClinGen ERepo {record.vcep_name or 'VCEP'} curated "
                        f"{criterion.criterion} for {record.classification}."
                    ),
                    citation=_first(record.citations),
                    provenance=_draft_provenance(match),
                    review_questions=[
                        "Confirm the rated variant and condition match the ClinGen ERepo assertion.",
                        "Confirm the VCEP criterion rationale is applicable to the current case.",
                        "Edit evidence_status to reviewed_applied only after qualified curator review.",
                    ],
                    limitations=[
                        "Draft is needs_more_info by default and is not applied ACMG evidence.",
                        "ClinGen ERepo criteria are external curated summaries and are not blindly imported.",
                        *match.limitations,
                    ],
                )
            )
        if not record.criteria_applied:
            drafts.append(
                ERepoReviewedEvidenceDraft(
                    source_erepo_record_id=record.record_id,
                    source_candidate_evidence_id=candidate_id,
                    rationale=(
                        f"ClinGen ERepo exact variant match classified as {record.classification}; "
                        "curator must decide whether any reviewed ACMG evidence should be applied."
                    ),
                    citation=_first(record.citations),
                    provenance=_draft_provenance(match),
                    review_questions=[
                        "Review the ERepo assertion and supporting evidence before selecting an ACMG criterion.",
                        "Do not apply the source classification itself as ACMG evidence.",
                    ],
                    limitations=[
                        "No source criterion summary was available in the ERepo record.",
                        "Draft is needs_more_info by default and is not applied ACMG evidence.",
                        *match.limitations,
                    ],
                )
            )
    return drafts


def _draft_provenance(match: ClinGenERepoMatch) -> dict[str, Any]:
    record = match.record
    return {
        "source": "ClinGen Evidence Repository",
        "source_erepo_record_id": record.record_id,
        "vcep_name": record.vcep_name,
        "classification": record.classification,
        "classification_date": str(record.classification_date) if record.classification_date else None,
        "classification_version": record.classification_version,
        "source_url": record.source_url,
        "api_endpoint": record.api_endpoint,
        "raw_snapshot_hash": record.raw_snapshot_hash,
        "match_level": match.match_level,
        "match_confidence": match.confidence,
        "matched_identifiers": match.matched_identifiers,
        "automatic_acmg_application": False,
    }


def _first(values: list[str]) -> str | None:
    return values[0] if values else None
