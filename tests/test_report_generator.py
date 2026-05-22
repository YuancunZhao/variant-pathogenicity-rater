from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from variant_pathogenicity_rater.reporting import generate_report
from variant_pathogenicity_rater.schemas import (
    AuditTrail,
    ClassificationResult,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    ReportFormat,
    ReportMode,
    ReviewFlag,
    Transcript,
    Variant,
)


ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

from tools.rate_variant import generate_report as generate_report_tool  # noqa: E402


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
            mane_select=True,
            canonical=True,
        ),
        hgvs_c="NM_000059.4:c.5946delT",
        hgvs_p="NP_000050.3:p.Ser1982ArgfsTer22",
    )


def _classification_result(
    *,
    final_classification: str = "vus",
    conflicting_evidence: list[str] | None = None,
    evidence_items: list[EvidenceItem] | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        result_id="report-test-result",
        variant=_variant(),
        final_classification=final_classification,
        evidence_items=evidence_items or [_population_evidence()],
        applied_combination_rule=None,
        pathogenic_evidence_summary=["PM2 candidate evidence was recorded."],
        benign_evidence_summary=[],
        conflicting_evidence=conflicting_evidence or [],
        limitations=["Offline example data only."],
        confidence=0.4,
        human_review_required=True,
        report_text="Legacy report text should not be used as the generated report body.",
        review_flags=[
            ReviewFlag(
                code="HUMAN_REVIEW_REQUIRED",
                message="All machine-generated conclusions require qualified human review.",
                severity="warning",
                blocking=True,
            )
        ],
        audit_trail=[
            AuditTrail(event_id="audit-report-test", event_type="classification_combined")
        ],
    )


def _population_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev-pop-001",
        code="PM2",
        strength=EvidenceStrength.MODERATE,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Variant is absent from the configured population dataset.",
        source=EvidenceSource(
            name="gnomAD",
            version="v4.1",
            retrieval_timestamp="2026-05-21T00:00:00Z",
            query={"variant_id": "13-32316461-AT-A"},
        ),
        confidence=0.72,
        requires_review=True,
        triggered_by=["population_frequency"],
    )


def _computational_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev-comp-001",
        code="PP3",
        strength=EvidenceStrength.SUPPORTING,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Multiple computational methods support a deleterious effect.",
        source=EvidenceSource(name="ComputationalPredictionEvaluator", version="0.1.0"),
        confidence=0.7,
        requires_review=True,
        triggered_by=["REVEL", "SpliceAI"],
    )


def _clinvar_conflict_evidence() -> EvidenceItem:
    return EvidenceItem(
        evidence_id="ev-clinvar-001",
        code="PP5",
        strength=EvidenceStrength.NONE,
        direction=EvidenceDirection.CONFLICTING,
        reason="ClinVar record has conflicting interpretations.",
        source=EvidenceSource(name="ClinVar", version="mock-clinvar-offline-v1"),
        confidence=0.5,
        requires_review=True,
        triggered_by=["clinvar_record"],
        supporting_data={"conflicting_interpretations": True, "candidate_only": True},
    )


def test_markdown_report_contains_required_sections_and_vus_note() -> None:
    report = generate_report(_classification_result(), output_format="markdown", mode="detailed")

    assert report.output_format == ReportFormat.MARKDOWN
    assert "## Variant Summary" in report.content
    assert "## Final Classification" in report.content
    assert "Variant of Uncertain Significance" in report.content
    assert "insufficient to support a pathogenic or benign classification" in report.content
    assert "Human Review Note" in report.content


def test_clinvar_conflict_is_prominently_reported() -> None:
    report = generate_report(
        _classification_result(
            conflicting_evidence=["ClinVar conflicting interpretations were observed."],
            evidence_items=[_population_evidence(), _clinvar_conflict_evidence()],
        ),
        output_format="plain_text",
        mode="laboratory",
    )

    assert report.summary.clinvar_conflict_detected is True
    assert "ClinVar conflict detected" in report.content
    assert "CONFLICTING EVIDENCE" in report.content


def test_computational_evidence_is_described_as_supporting_only() -> None:
    report = generate_report(
        _classification_result(evidence_items=[_computational_evidence()]),
        output_format="json",
        mode="concise",
    )

    rendered = json.dumps(report.content)
    assert "supporting evidence only" in rendered
    assert "determinative" in rendered
    assert report.content["final_classification"]["machine_proposal_only"] is True
    assert report.content["human_review_required"] is True
    assert report.content["data_source_summary"][0]["name"] == "ComputationalPredictionEvaluator"


def test_all_text_modes_include_auditable_required_sections() -> None:
    required_sections = [
        "Variant Summary",
        "Final Classification",
        "Triggered ACMG Evidence",
        "Candidate / Review-Note Evidence",
        "Conflicting Evidence",
        "Limitations",
        "Data Source Summary",
        "Human Review Note",
    ]

    for mode in ReportMode:
        report = generate_report(_classification_result(), output_format="markdown", mode=mode)
        for section in required_sections:
            assert section in report.content
        assert "rationale:" in report.content
        assert "source:" in report.content


def test_mcp_generate_report_tool_returns_selected_format() -> None:
    payload = {
        "classification_result": json.loads(_classification_result().model_dump_json()),
        "format": "plain_text",
        "mode": "clinician",
    }

    response = asyncio.run(generate_report_tool(payload))

    assert response["status"] == "ok"
    assert "plain_text" in response
    assert response["json_summary"]["human_review_note"]
    assert "Human Review Note" in response["plain_text"]


def test_report_separates_applied_evidence_from_candidate_evidence() -> None:
    candidate = EvidenceItem(
        evidence_id="ev-lit-001",
        code="PS3",
        strength=EvidenceStrength.NONE,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Literature functional claim is candidate-only pending review.",
        source=EvidenceSource(name="Literature", version="fixture-v1"),
        confidence=0.4,
        requires_review=True,
        triggered_by=["literature"],
        supporting_data={"candidate_only": True, "evidence_status": "candidate"},
    )
    report = generate_report(
        _classification_result(evidence_items=[_population_evidence(), candidate]),
        output_format="json",
        mode="detailed",
    )
    text_report = generate_report(
        _classification_result(evidence_items=[_population_evidence(), candidate]),
        output_format="markdown",
        mode="detailed",
    )

    assert [item["evidence_id"] for item in report.content["evidence"]["applied_items"]] == [
        "ev-pop-001"
    ]
    assert [item["evidence_id"] for item in report.content["evidence"]["candidate_items"]] == [
        "ev-lit-001"
    ]
    assert "ev-lit-001" not in text_report.content.split("## Candidate / Review-Note Evidence")[0]
    assert "candidate/review-note only; not used in classification" in text_report.content
