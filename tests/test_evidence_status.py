from __future__ import annotations

from variant_pathogenicity_rater.evidence.clinvar import CLINVAR_REVIEW_NOTE
from variant_pathogenicity_rater.evidence.status import (
    EvidenceDisplayStatus,
    build_evidence_status_view,
    is_combiner_eligible,
    split_evidence_by_status,
    summarize_evidence_status,
)
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.reporting.generator import generate_report
from variant_pathogenicity_rater.schemas import (
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.classification import ClassificationResult


def test_applied_evidence_item_is_applied_and_combiner_eligible(evidence_factory) -> None:
    item = evidence_factory("PVS1", "very_strong", "pathogenic")

    view = build_evidence_status_view(item)

    assert view.display_status == EvidenceDisplayStatus.APPLIED
    assert view.is_applied is True
    assert view.combiner_eligible is True


def test_candidate_only_evidence_item_is_not_combiner_eligible(evidence_factory) -> None:
    item = evidence_factory("BA1", "none", "benign")
    item.candidate_only = True
    item.applied = False
    item.supporting_data["candidate_only"] = True

    view = build_evidence_status_view(item)

    assert view.display_status == EvidenceDisplayStatus.CANDIDATE_ONLY
    assert view.combiner_eligible is False


def test_strength_none_is_not_combiner_eligible(evidence_factory) -> None:
    item = evidence_factory("PP3", "none", "pathogenic")

    view = build_evidence_status_view(item)

    assert view.combiner_eligible is False
    assert view.reason == "strength=none is not combiner eligible."


def test_clinvar_pp5_candidate_remains_review_note_not_combiner_eligible() -> None:
    item = EvidenceItem(
        evidence_id="clinvar-candidate-pp5",
        code="PP5",
        strength="none",
        direction="neutral",
        reason="ClinVar assertion is a candidate review note only.",
        source=EvidenceSource(name="ClinVar", version="fixture"),
        confidence=0.4,
        requires_review=True,
        candidate_only=True,
        applied=False,
        supporting_data={
            "candidate_only": True,
            "applied": False,
            "evidence_status": "candidate",
            "review_note": CLINVAR_REVIEW_NOTE,
        },
    )

    view = build_evidence_status_view(item)

    assert view.display_status == EvidenceDisplayStatus.REVIEW_NOTE
    assert view.combiner_eligible is False


def test_literature_suggested_evidence_is_not_combiner_eligible() -> None:
    suggestion = {
        "source_candidate_evidence_id": "literature-suggested-PS3-abc",
        "code": "PS3_candidate",
        "candidate_code": "PS3_candidate",
        "suggested_strength": "strong",
        "candidate_only": True,
        "requires_manual_review": True,
    }

    view = build_evidence_status_view(suggestion)

    assert view.display_status == EvidenceDisplayStatus.CANDIDATE_ONLY
    assert view.combiner_eligible is False


def test_erepo_candidate_and_draft_are_not_combiner_eligible() -> None:
    candidate = {
        "evidence_id": "erepo-candidate",
        "code": "PS1",
        "strength": "none",
        "direction": "neutral",
        "source": {"name": "ClinGen Evidence Repository"},
        "candidate_only": True,
        "applied": False,
        "supporting_data": {"review_note": "ERepo review note.", "candidate_only": True},
    }
    draft = {
        "source_candidate_evidence_id": "erepo-candidate",
        "acmg_code": "PS1",
        "strength": "strong",
        "direction": "pathogenic",
        "evidence_status": "needs_more_info",
    }

    assert build_evidence_status_view(candidate).combiner_eligible is False
    draft_view = build_evidence_status_view(draft)
    assert draft_view.display_status == EvidenceDisplayStatus.NEEDS_MORE_INFO
    assert draft_view.combiner_eligible is False


def test_converted_reviewed_applied_item_is_applied(evidence_factory) -> None:
    item = evidence_factory("PS3", "strong", "pathogenic", source_name="manual_reviewed_evidence")
    item.supporting_data["reviewed_evidence"] = {
        "evidence_status": "reviewed_applied",
        "rationale": "Curator reviewed functional assay.",
        "review_date": "2026-06-05",
    }
    item.supporting_data["evidence_status"] = "reviewed_applied"
    item.candidate_only = False

    view = build_evidence_status_view(item)

    assert view.display_status == EvidenceDisplayStatus.APPLIED
    assert view.reviewed_status == "reviewed_applied"
    assert view.combiner_eligible is True


def test_reviewed_rejected_needs_more_info_and_invalid_are_not_applied() -> None:
    rejected = {"acmg_code": "PP1", "evidence_status": "reviewed_rejected"}
    pending = {"acmg_code": "PS4", "evidence_status": "needs_more_info"}
    invalid = {
        "acmg_code": "PS3",
        "strength": "none",
        "direction": "pathogenic",
        "evidence_status": "reviewed_applied",
    }

    assert build_evidence_status_view(rejected).display_status == EvidenceDisplayStatus.REVIEWED_REJECTED
    assert build_evidence_status_view(rejected).combiner_eligible is False
    assert build_evidence_status_view(pending).display_status == EvidenceDisplayStatus.NEEDS_MORE_INFO
    assert build_evidence_status_view(pending).combiner_eligible is False
    assert build_evidence_status_view(invalid).display_status == EvidenceDisplayStatus.INVALID
    assert build_evidence_status_view(invalid).combiner_eligible is False


def test_split_evidence_by_status_matches_legacy_grouping(evidence_factory) -> None:
    applied = evidence_factory("PVS1", "very_strong", "pathogenic")
    candidate = evidence_factory("PP3", "none", "pathogenic")
    candidate.candidate_only = True
    candidate.applied = False
    candidate.supporting_data["candidate_only"] = True

    split = split_evidence_by_status([applied, candidate])

    assert split["applied"] == [applied]
    assert split["review_note"] == [candidate]


def test_canonical_evidence_status_summary_contains_extended_counts(evidence_factory) -> None:
    applied = evidence_factory("PVS1", "very_strong", "pathogenic")
    candidate = evidence_factory("PP3", "none", "pathogenic")
    candidate.candidate_only = True
    candidate.applied = False
    candidate.supporting_data["candidate_only"] = True
    reviewed = [
        {
            "acmg_code": "PS3",
            "evidence_status": "reviewed_applied",
            "strength": "strong",
            "direction": "pathogenic",
            "rationale": "Curator reviewed assay.",
            "review_date": "2026-06-05",
        },
        {"acmg_code": "PP1", "evidence_status": "reviewed_rejected"},
        {"acmg_code": "PS4", "evidence_status": "needs_more_info"},
        {"acmg_code": "PM3", "evidence_status": "reviewed_applied", "strength": "none", "direction": "pathogenic"},
    ]

    summary = summarize_evidence_status([applied, candidate], reviewed)

    assert summary["applied_count"] == 1
    assert summary["candidate_count"] == 1
    assert summary["reviewed_applied_count"] == 1
    assert summary["reviewed_rejected_count"] == 1
    assert summary["needs_more_info_count"] == 1
    assert summary["invalid_count"] == 1
    assert summary["combiner_eligible_count"] == 1
    assert summary["codes_by_status"]["applied"] == ["PVS1"]


def test_pipeline_summary_and_legacy_evidence_fields_are_unchanged() -> None:
    result = rate_variant(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68_69delAG",
            "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
            "chromosome": "17",
            "position": 43092919,
            "ref": "AG",
            "alt": "A",
            "disease": "Hereditary breast and ovarian cancer",
            "inheritance": "autosomal dominant",
        }
    )

    assert result["evidence"]["applied"] == result["applied_evidence"]
    assert result["evidence"]["review_note"] == result["review_note_evidence"]
    assert result["classification"]["final_classification"] == result["final_classification"]
    summary = result["evidence"]["evidence_status_summary"]
    assert summary["applied_count"] == len(result["applied_evidence"])
    assert summary["review_note_count"] + summary["candidate_count"] == len(result["review_note_evidence"])


def test_report_grouping_unchanged(evidence_factory, snv_variant) -> None:
    applied = evidence_factory("PVS1", "very_strong", "pathogenic")
    candidate = evidence_factory("PP3", "none", "pathogenic")
    candidate.candidate_only = True
    candidate.applied = False
    candidate.supporting_data["candidate_only"] = True
    result = ClassificationResult(
        result_id="status-report-test",
        variant=snv_variant,
        final_classification="likely_pathogenic",
        applied_combination_rule="PVS1",
        confidence=0.8,
        evidence_items=[applied, candidate],
        report_text="fixture",
        human_review_required=True,
    )

    report = generate_report(result, output_format="json")

    assert len(report.content["applied_evidence"]["items"]) == 1
    assert len(report.content["review_note_evidence"]["items"]) == 1


def test_batch_evidence_summary_unchanged() -> None:
    batch = rate_variant_batch(
        {
            "format": "jsonl",
            "data": '{"gene":"BRCA1","hgvs_c":"NM_007294.4:c.68_69delAG","disease":"HBOC","inheritance":"autosomal dominant"}',
        }
    )

    record = batch["results"][0]
    assert record["canonical_summary"]["evidence"]["applied"] == record["applied_evidence"]
    assert record["canonical_summary"]["evidence"]["review_note"] == record["review_note_evidence"]
