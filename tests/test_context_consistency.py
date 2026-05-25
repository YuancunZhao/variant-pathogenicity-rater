from __future__ import annotations

import json

from variant_pathogenicity_rater.context_consistency import evaluate_context_consistency
from variant_pathogenicity_rater.data_sources.provenance import ProvenanceMetadata
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.schemas import (
    ClinVarRecord,
    EvidenceSource,
    GeneDiseaseContext,
    PopulationFrequency,
    Transcript,
    TranscriptSelection,
    Variant,
    VariantAnnotation,
)


def _variant(**overrides: object) -> Variant:
    payload = {
        "variant_id": "GRCh38-17-43092919-A-G",
        "genome_build": "GRCh38",
        "variant_type": "snv",
        "chrom": "17",
        "pos": 43092919,
        "ref": "A",
        "alt": "G",
        "gene_symbol": "BRCA1",
        "transcript": {
            "accession": "NM_007294",
            "version": "4",
            "gene_symbol": "BRCA1",
            "hgvs_c": "NM_007294.4:c.68A>G",
            "hgvs_p": "NP_009225.1:p.Glu23Gly",
            "consequence": "missense_variant",
        },
        "hgvs_c": "NM_007294.4:c.68A>G",
        "hgvs_p": "NP_009225.1:p.Glu23Gly",
    }
    payload.update(overrides)
    return Variant.model_validate(payload)


def _context(**overrides: object) -> GeneDiseaseContext:
    payload = {
        "gene": "BRCA1",
        "disease": "Hereditary breast ovarian cancer syndrome",
        "inheritance": "autosomal dominant",
        "population_ancestry": "East Asian",
    }
    payload.update(overrides)
    return GeneDiseaseContext.model_validate(payload)


def _annotation(**overrides: object) -> VariantAnnotation:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68A>G",
        "hgvs_p": "NP_009225.1:p.Glu23Gly",
        "consequence": "missense_variant",
        "consequence_terms": ["missense_variant"],
        "annotation_source": "test_annotation",
        "provenance": ProvenanceMetadata(data_source="test_annotation", raw_record_hash="abc123"),
        "raw_fields": {},
    }
    payload.update(overrides)
    return VariantAnnotation.model_validate(payload)


def _clinvar(condition: str) -> ClinVarRecord:
    return ClinVarRecord(
        source=EvidenceSource(name="ClinVar", query={"genome_build": "GRCh38"}),
        clinical_significance="Pathogenic",
        condition=condition,
        conditions=[condition],
    )


def _population(**overrides: object) -> PopulationFrequency:
    payload = {
        "overall_af": 0.001,
        "max_pop_af": 0.001,
        "population_name": "European non-Finnish",
        "allele_number": 100000,
        "data_source": "gnomAD",
        "genome_build": "GRCh38",
    }
    payload.update(overrides)
    return PopulationFrequency.model_validate(payload)


def test_gene_mismatch_conflicts() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(),
        annotation_records=[_annotation(gene="TP53")],
    )

    assert result.status == "conflict"
    assert any(check.check_name == "user_gene_vs_annotation_gene" for check in result.conflicts)
    assert result.review_required is True


def test_transcript_mismatch_conflicts() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(),
        annotation_records=[_annotation(transcript="NM_000546.6")],
    )

    assert any(
        check.check_name == "user_transcript_vs_annotation_transcript"
        for check in result.conflicts
    )


def test_hgvs_transcript_prefix_mismatch_conflicts() -> None:
    result = evaluate_context_consistency(
        _variant(hgvs_c="NM_000546.6:c.68A>G"),
        _context(),
        annotation_records=[],
    )

    assert any(
        check.check_name == "hgvs_transcript_prefix_vs_transcript_field"
        for check in result.conflicts
    )


def test_clinvar_condition_mismatch_conflicts() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(disease="Li-Fraumeni syndrome"),
        clinvar_records=[_clinvar("Hereditary breast ovarian cancer syndrome")],
    )

    assert any(check.check_name == "clinvar_condition_vs_user_disease" for check in result.conflicts)


def test_population_ancestry_mismatch_flags_review() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(population_ancestry="East Asian"),
        population_records=[_population(population_name="European non-Finnish")],
    )

    assert any(
        check.check_name == "population_ancestry_context_mismatch"
        for check in result.warnings
    )


def test_genome_build_mismatch_conflicts() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(),
        population_records=[_population(genome_build="GRCh37")],
    )

    assert any(
        check.check_name == "provider_genome_build_vs_input_genome_build"
        for check in result.conflicts
    )


def test_missing_inheritance_is_insufficient() -> None:
    result = evaluate_context_consistency(_variant(), _context(inheritance=None))

    assert result.status == "insufficient"
    assert any(
        check.check_name == "inheritance_missing_or_inconsistent"
        for check in result.warnings
    )


def test_multiple_annotation_genes_conflict() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(),
        annotation_records=[_annotation(gene="BRCA1"), _annotation(gene="BRCA2")],
    )

    assert any(check.check_name == "multiple_annotation_genes" for check in result.conflicts)


def test_selected_transcript_mismatch_conflicts() -> None:
    result = evaluate_context_consistency(
        _variant(),
        _context(),
        transcript_selection=TranscriptSelection(
            selected_transcript="NM_000546.6",
            selected_gene="TP53",
            selection_reason="test",
            selection_confidence=0.9,
        ),
    )

    assert any(
        check.check_name == "selected_transcript_vs_variant_transcript"
        for check in result.conflicts
    )


def test_protein_hgvs_without_context_is_insufficient() -> None:
    result = evaluate_context_consistency(
        _variant(gene_symbol=None, transcript=None, hgvs_p="p.Glu23Gly"),
        None,
    )

    assert any(
        check.check_name == "protein_hgvs_gene_transcript_ambiguity"
        for check in result.warnings
    )


def test_consequence_variant_type_mismatch_warns() -> None:
    result = evaluate_context_consistency(
        _variant(variant_type="snv"),
        _context(),
        annotation_records=[_annotation(consequence="frameshift_variant", consequence_terms=["frameshift_variant"])],
    )

    assert any(
        check.check_name == "annotation_consequence_vs_variant_type"
        for check in result.warnings
    )


def test_consistency_conflict_does_not_change_classification() -> None:
    base = _pipeline_payload()
    clean = rate_variant(base)
    conflicted = rate_variant(
        {
            **base,
            "options": {
                **base["options"],
                "include_transcript_selection": True,
                "annotations": [
                    _annotation(gene="TP53", transcript="NM_000546.6").model_dump(mode="json")
                ],
            },
        }
    )

    assert conflicted["context_consistency"]["status"] == "conflict"
    assert conflicted["final_classification"] == clean["final_classification"]


def test_report_includes_context_consistency_section() -> None:
    result = rate_variant(
        {
            **_pipeline_payload(),
            "options": {
                "include_transcript_selection": True,
                "annotations": [_annotation(gene="TP53").model_dump(mode="json")],
            },
        }
    )

    assert "## Context Consistency" in result["report_text"]
    assert "user_gene_vs_annotation_gene" in result["report_text"]
    assert result["report"]["summary"]["context_consistency"]["status"] == "conflict"


def test_batch_preserves_per_record_context_consistency() -> None:
    record = _pipeline_payload()
    record["options"] = {
        "include_transcript_selection": True,
        "annotations": [_annotation(gene="TP53").model_dump(mode="json")],
    }
    result = rate_variant_batch({"records": [record]})

    summary = result["results"][0]["context_consistency_summary"]
    assert summary["status"] == "conflict"
    assert summary["conflict_count"] >= 1


def _pipeline_payload() -> dict:
    return {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68A>G",
        "hgvs_p": "NP_009225.1:p.Glu23Gly",
        "chromosome": "17",
        "position": 43092919,
        "ref": "A",
        "alt": "G",
        "disease": "Hereditary breast ovarian cancer syndrome",
        "inheritance": "autosomal dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "mock_supplemental_evidence_items": [],
        },
    }
