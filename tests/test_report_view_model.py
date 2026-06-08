from __future__ import annotations

from pathlib import Path

from variant_pathogenicity_rater.reporting.view_model_builder import build_report_view_model
from variant_pathogenicity_rater.schemas import (
    ClassificationResult,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    ReviewFlag,
    Transcript,
    Variant,
)


def _variant() -> Variant:
    return Variant(
        variant_id="GRCh38-13-32316461-AT-A",
        genome_build="GRCh38",
        variant_type="small_deletion",
        chrom="13",
        pos=32316461,
        ref="AT",
        alt="A",
        gene_symbol="BRCA2",
        transcript=Transcript(
            accession="NM_000059",
            version="4",
            gene_symbol="BRCA2",
            hgvs_c="NM_000059.4:c.5946delT",
            hgvs_p="NP_000050.3:p.Ser1982ArgfsTer22",
            consequence="frameshift_variant",
        ),
        hgvs_c="NM_000059.4:c.5946delT",
        hgvs_p="NP_000050.3:p.Ser1982ArgfsTer22",
    )


def _applied_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev-pop-001",
        code="PM2",
        strength=EvidenceStrength.MODERATE,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Population evidence passed applied gates.",
        source=EvidenceSource(name="gnomAD", version="v4"),
        confidence=0.7,
        requires_review=True,
        triggered_by=["population_frequency"],
    )


def _candidate_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev-lit-001",
        code="PS3",
        strength=EvidenceStrength.NONE,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Literature claim requires curator review.",
        source=EvidenceSource(name="Literature", version="fixture-v1"),
        confidence=0.4,
        requires_review=True,
        triggered_by=["literature"],
        candidate_only=True,
        applied=False,
        supporting_data={"candidate_only": True, "evidence_status": "candidate"},
    )


def _classification_result() -> ClassificationResult:
    return ClassificationResult(
        result_id="report-view-model-test",
        variant=_variant(),
        final_classification="vus",
        evidence_items=[_applied_evidence(), _candidate_evidence()],
        applied_combination_rule=None,
        pathogenic_evidence_summary=["PM2 was applied."],
        benign_evidence_summary=[],
        conflicting_evidence=[],
        limitations=["Offline fixture."],
        confidence=0.42,
        human_review_required=True,
        report_text="not used",
        review_flags=[
            ReviewFlag(
                code="HUMAN_REVIEW_REQUIRED",
                message="Human review is required.",
                severity="warning",
                blocking=True,
            )
        ],
    )


def test_report_view_model_maps_evidence_classification_and_review() -> None:
    vm = build_report_view_model(_classification_result())

    assert vm.variant.gene == "BRCA2"
    assert vm.variant.transcript == "NM_000059.4"
    assert vm.classification.final_classification == "vus"
    assert vm.classification.confidence == 0.42
    assert vm.classification.human_review_required is True
    assert len(vm.evidence) == 2
    assert vm.evidence[0].display_status == "applied"
    assert vm.evidence[1].display_status == "candidate_only"
    assert [item.entry.evidence_id for item in vm.evidence_sections.counted] == ["ev-pop-001"]
    assert [item.entry.evidence_id for item in vm.evidence_sections.review_note] == ["ev-lit-001"]
    assert vm.evidence_sections.review_note[0].display_status == "candidate_only"
    assert vm.summary.triggered_acmg_evidence[0].evidence_id == "ev-pop-001"
    assert vm.summary.candidate_acmg_evidence[0].evidence_id == "ev-lit-001"
    assert vm.review.blocking_reasons == ["Human review is required."]


def test_report_view_model_maps_provider_runtime_from_rate_variant_result() -> None:
    result = _classification_result().model_dump(mode="json")
    rate_result = {
        "classification_result": result,
        "step_results": {
            "provider_runtime": {
                "clinvar": {
                    "provider_name": "clinvar",
                    "requested_mode": "online",
                    "configured_mode": "online",
                    "attempted": True,
                    "outcome": "success",
                    "records_count": 1,
                    "limitations": [],
                }
            }
        },
    }

    vm = build_report_view_model(rate_result)

    assert len(vm.providers) == 1
    assert vm.providers[0].provider_name == "clinvar"
    assert vm.providers[0].requested_mode == "online"
    assert vm.providers[0].configured_mode == "online"
    assert vm.providers[0].outcome == "success"
    assert vm.providers[0].records_count == 1


def test_report_generator_does_not_parse_internal_evidence_status_fields() -> None:
    generator = Path("src/variant_pathogenicity_rater/reporting/generator.py").read_text(
        encoding="utf-8"
    )

    assert "supporting_data" not in generator
    assert "candidate_only" not in generator
    assert "evidence_items" not in generator
    assert "evidence_status" not in generator
    assert "provider_mode_summary" not in generator
    assert "step_results" not in generator
    assert "build_evidence_status_view" not in generator
