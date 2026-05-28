from __future__ import annotations

import json

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pipeline.real_world import run_annotation_batch_workflow
from variant_pathogenicity_rater.ps1_pm5 import generate_ps1_pm5_evidence
from variant_pathogenicity_rater.pvs1 import generate_pvs1_evidence
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord, EvidenceSource
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Transcript, Variant
from variant_pathogenicity_rater.transcript_support import (
    TranscriptMetadata,
    validate_transcript_metadata,
)


def _variant(
    *,
    transcript: str = "NM_007294.4",
    hgvs_p: str = "NP_009225.1:p.Glu23ValfsTer17",
    consequence: str = "frameshift_variant",
) -> Variant:
    accession, version = transcript.split(".", 1)
    return Variant(
        variant_id="GRCh38-17-43124027-CA-C",
        genome_build="GRCh38",
        variant_type="small_deletion",
        chrom="17",
        pos=43124027,
        ref="CA",
        alt="C",
        gene_symbol="BRCA1",
        hgvs_c=f"{transcript}:c.68_69delAG",
        hgvs_p=hgvs_p,
        transcript=Transcript(
            accession=accession,
            version=version,
            gene_symbol="BRCA1",
            hgvs_c=f"{transcript}:c.68_69delAG",
            hgvs_p=hgvs_p,
            consequence=consequence,
            mane_select=True,
            canonical=True,
        ),
    )


def _missense_variant(*, hgvs_p: str = "NP_000001.1:p.Lys26Arg") -> Variant:
    return Variant(
        variant_id="GRCh38-1-123-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=123,
        ref="A",
        alt="G",
        gene_symbol="GENE1",
        transcript=Transcript(accession="NM_000001", version="1", gene_symbol="GENE1"),
        hgvs_c="NM_000001.1:c.76A>G",
        hgvs_p=hgvs_p,
    )


def _annotation(**updates) -> VariantAnnotation:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "consequence": "frameshift_variant",
        "exon": "2/24",
        "canonical": True,
        "mane_select": True,
        "transcript_biotype": "protein_coding",
        "annotation_source": "pytest",
        "provenance": {"data_source": "pytest", "source_version": "v1", "raw_record_hash": "mane"},
        "raw_fields": {"case": "mane"},
    }
    payload.update(updates)
    return VariantAnnotation.model_validate(payload)


def _context() -> GeneDiseaseContext:
    return GeneDiseaseContext.model_validate(
        {
            "gene": "BRCA1",
            "disease": "Hereditary breast and ovarian cancer syndrome",
            "inheritance": "autosomal_dominant",
            "lof_is_known_mechanism": True,
            "transcript_is_biologically_relevant": True,
            "nmd_prediction_available": True,
            "nmd_predicted": True,
            "last_exon_information": {"is_in_last_exon": False, "exon_number": 2, "total_exons": 24},
        }
    )


def _metadata(**updates) -> TranscriptMetadata:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "transcript_version": "4",
        "mane_status": "MANE_Select",
        "canonical": True,
        "protein_coding": True,
        "exon_count": 24,
        "cds_length": 5592,
        "transcript_source": "RefSeq/MANE",
        "genome_build": "GRCh38",
        "protein_accession": "NP_009225.1",
        "transcript_status": "current",
        "nmd_relevance": "exon-aware",
        "tags": ["MANE_Select", "RefSeq"],
        "source_version": "mane-test-v1",
        "parser_version": "pytest-parser-v1",
        "raw_snapshot_ref": "sha256:mane",
        "retrieval_timestamp": "2026-05-28T00:00:00Z",
    }
    payload.update(updates)
    return TranscriptMetadata.model_validate(payload)


def _clinvar_missense(*, hgvs_p: str = "NP_000001.1:p.Lys26Arg") -> ClinVarRecord:
    return ClinVarRecord(
        source=EvidenceSource(name="ClinVar", version="test", database_id="cv-1"),
        variation_id="cv-1",
        gene_symbol="GENE1",
        transcript="NM_000001.1",
        hgvs_c="NM_000001.1:c.77A>G",
        hgvs_p=hgvs_p,
        protein_change=hgvs_p,
        chromosome="1",
        position=124,
        ref="A",
        alt="G",
        genome_build="GRCh38",
        clinical_significance="Pathogenic",
        review_status="reviewed by expert panel",
        review_stars=3,
        submitter_count=3,
        condition="Example disease",
        conditions=["Example disease"],
        germline_or_somatic="germline",
    )


def test_transcript_mismatch_review_flag_and_no_silent_replacement() -> None:
    result = validate_transcript_metadata(
        variant=_variant(transcript="NM_007299.4"),
        context=_context(),
        transcript_records=[_metadata()],
    )

    assert result.status == "conflict"
    assert result.input_transcript == "NM_007299.4"
    assert result.matched_record is None
    assert result.user_transcript_preserved is True
    assert any(flag.code == "USER_TRANSCRIPT_NOT_IN_TRANSCRIPT_FIXTURE" for flag in result.review_flags)


def test_mane_preferred_note_is_recommendation_only_without_user_transcript() -> None:
    variant = _variant()
    variant.transcript = None
    result = validate_transcript_metadata(
        variant=variant,
        context=None,
        transcript_records=[_metadata()],
    )

    assert result.status == "insufficient"
    assert any(flag.code == "MANE_SELECT_TRANSCRIPT_RECOMMENDED" for flag in result.review_flags)
    assert result.mane_select_candidates[0]["transcript"] == "NM_007294.4"


def test_version_mismatch_is_review_flag() -> None:
    result = validate_transcript_metadata(
        variant=_variant(transcript="NM_007294.3"),
        context=_context(),
        transcript_records=[_metadata()],
    )

    assert result.status == "conflict"
    assert any(flag.code == "TRANSCRIPT_VERSION_MISMATCH" for flag in result.review_flags)


def test_non_coding_transcript_blocks_applied_pvs1() -> None:
    validation = validate_transcript_metadata(
        variant=_variant(),
        context=_context(),
        transcript_records=[_metadata(protein_coding=False)],
    )
    item, decision = generate_pvs1_evidence(
        _variant(),
        annotation=_annotation(),
        gene_disease_context=_context(),
        transcript_validation=validation,
    )

    assert item is not None
    assert decision.applied is False
    assert item.candidate_only is True
    assert any(flag.code == "NON_CODING_TRANSCRIPT_METADATA" for flag in decision.review_flags)


def test_deprecated_transcript_creates_limitation() -> None:
    validation = validate_transcript_metadata(
        variant=_variant(),
        context=_context(),
        transcript_records=[_metadata(transcript_status="deprecated")],
    )

    assert validation.status == "conflict"
    assert any(flag.code == "DEPRECATED_TRANSCRIPT_METADATA" for flag in validation.review_flags)
    assert any("Deprecated transcript" in limitation for limitation in validation.limitations)


def test_protein_mismatch_keeps_ps1_candidate_only() -> None:
    validation = validate_transcript_metadata(
        variant=_missense_variant(hgvs_p="NP_999999.1:p.Lys26Arg"),
        context=GeneDiseaseContext(gene="GENE1", disease="Example disease"),
        transcript_records=[
            _metadata(
                gene="GENE1",
                transcript="NM_000001.1",
                transcript_version="1",
                protein_accession="NP_000001.1",
            )
        ],
    )
    items, decisions = generate_ps1_pm5_evidence(
        variant=_missense_variant(hgvs_p="NP_999999.1:p.Lys26Arg"),
        context=GeneDiseaseContext(gene="GENE1", disease="Example disease"),
        clinvar_records=[_clinvar_missense(hgvs_p="NP_999999.1:p.Lys26Arg")],
        transcript_validation=validation,
    )

    assert decisions[0].applied is False
    assert decisions[0].candidate_only is True
    assert any("protein accession mismatch" in reason.lower() for reason in decisions[0].blocking_reasons)
    assert items[0].candidate_only is True


def test_report_batch_and_pipeline_expose_transcript_validation() -> None:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43124027,
        "ref": "CA",
        "alt": "C",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "include_transcript_selection": True,
            "annotations": [_annotation().model_dump(mode="json")],
            "transcript_metadata_records": [_metadata().model_dump(mode="json")],
            "gene_disease_context": _context().model_dump(mode="json"),
        },
    }
    result = rate_variant(payload)
    batch = rate_variant_batch({"records": [payload]})

    assert result["transcript_validation"]["matched_record"]["protein_accession"] == "NP_009225.1"
    assert result["classification_result"]["transcript_validation"]["status"] in {"ok", "warning"}
    assert "Transcript Selection / MANE Validation" in result["report_text"]
    assert result["provenance"]["transcript_validation"]["validator"] == "local_transcript_validation_v1"
    assert batch["results"][0]["transcript_validation_summary"]["matched_transcript"] == "NM_007294.4"


def test_annotated_batch_preserves_transcript_validation_summary() -> None:
    text = (
        "gene,transcript,hgvs_c,hgvs_p,chromosome,position,ref,alt,consequence,canonical,mane_select,transcript_biotype\n"
        "BRCA1,NM_007294.4,NM_007294.4:c.68_69delAG,NP_009225.1:p.Glu23ValfsTer17,17,43124027,CA,C,frameshift_variant,true,true,protein_coding\n"
    )
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "input_text": text,
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_clinvar": False,
                "include_literature": False,
                "transcript_metadata_records": [_metadata().model_dump(mode="json")],
                "gene_disease_context": _context().model_dump(mode="json"),
            },
        }
    )

    summary = result["results"][0]["transcript_validation_summary"]
    assert summary["matched_transcript"] == "NM_007294.4"
    assert summary["protein_accession_match"] is True


def test_transcript_validation_does_not_enter_combiner_directly() -> None:
    variant = _variant()
    base = classify_acmg([], variant, _context(), [])
    with_flag = classify_acmg(
        [],
        variant,
        _context(),
        ["Transcript validation conflict detected; human review is required."],
    )

    assert base.final_classification == with_flag.final_classification
    assert base.evidence_items == with_flag.evidence_items == []
