from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from variant_pathogenicity_rater.schemas import (
    ACMGClassification,
    AuditTrail,
    ClinVarRecord,
    ClassificationResult,
    ComputationalPrediction,
    EvidenceCode,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    GeneDiseaseContext,
    LiteratureEvidence,
    PopulationFrequency,
    Transcript,
    Variant,
)


ROOT = Path(__file__).resolve().parents[1]


def test_variant_and_context_are_json_serializable() -> None:
    payload = json.loads((ROOT / "examples" / "example_input.json").read_text())

    variant = Variant.model_validate(payload["variant"])
    context = GeneDiseaseContext.model_validate(payload["gene_disease_context"])

    assert variant.variant_type == "small_deletion"
    assert context.gene_symbol == "BRCA2"
    assert json.loads(variant.model_dump_json())["genome_build"] == "GRCh38"


def test_evidence_item_required_contract() -> None:
    source = EvidenceSource(name="ClinVar", version="2026-05", query={"term": "BRCA2"})
    audit = AuditTrail(event_id="audit-1", event_type="retrieved", tool_name="query_clinvar")

    item = EvidenceItem(
        evidence_id="ev-1",
        code=EvidenceCode.PVS1,
        strength=EvidenceStrength.VERY_STRONG,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Candidate loss-of-function evidence captured for review.",
        source=source,
        confidence=0.85,
        requires_review=True,
        triggered_by=["clinvar_record"],
        supporting_data={"variation_id": "123"},
        audit_trail=[audit],
    )

    dumped = json.loads(item.model_dump_json())
    assert dumped["code"] == "PVS1"
    assert dumped["strength"] == "very_strong"
    assert dumped["audit_trail"][0]["event_id"] == "audit-1"


def test_classification_result_required_contract_from_example() -> None:
    payload = json.loads((ROOT / "examples" / "example_output.json").read_text())

    result = ClassificationResult.model_validate(payload)

    assert result.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert result.human_review_required is True
    assert result.evidence_items[0].requires_review is True
    assert json.loads(result.model_dump_json())["final_classification"] == "vus"


def test_invalid_snv_allele_lengths_are_rejected() -> None:
    with pytest.raises(ValidationError, match="SNV variants must have one-base"):
        Variant(
            variant_id="bad-snv",
            genome_build="GRCh38",
            variant_type="snv",
            chrom="1",
            pos=1,
            ref="AT",
            alt="A",
        )


def test_confidence_must_be_probability() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="ev-bad",
            code="BP4",
            strength="supporting",
            direction="benign",
            reason="Out-of-range confidence should fail.",
            source=EvidenceSource(name="Predictor"),
            confidence=1.1,
        )


def test_transcript_minimal_payload() -> None:
    transcript = Transcript(accession="NM_000059", gene_symbol="BRCA2")
    assert transcript.model_dump()["canonical"] is False


def test_source_specific_evidence_models_are_serializable() -> None:
    source = EvidenceSource(name="example_source")
    records = [
        PopulationFrequency(
            source=source,
            overall_af=0.001,
            max_pop_af=0.001,
            population_name="global",
            allele_count=10,
            allele_number=10000,
            homozygote_count=0,
            hemizygote_count=0,
            data_source="example_source",
        ),
        ComputationalPrediction(source=source, method="REVEL", score=0.8, prediction="deleterious"),
        ClinVarRecord(source=source, clinical_significance="Pathogenic", conditions=["Example"]),
        LiteratureEvidence(
            source=source,
            citation="PMID:123",
            title="Example paper",
            year=2024,
            finding="Segregation noted.",
        ),
    ]

    for record in records:
        dumped = json.loads(record.model_dump_json())
        assert dumped["source"]["name"] == "example_source"
