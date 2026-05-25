from __future__ import annotations

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.data_sources.provenance import provenance_from_raw_record
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pvs1 import generate_pvs1_evidence
from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.evidence import EvidenceDirection, EvidenceItem, EvidenceSource, EvidenceStrength
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, LastExonInformation, Transcript, Variant


def _brca1_variant() -> Variant:
    return Variant(
        variant_id="GRCh38-17-43124027-CA-C",
        genome_build="GRCh38",
        variant_type="small_deletion",
        chrom="17",
        pos=43124027,
        ref="CA",
        alt="C",
        gene_symbol="BRCA1",
        hgvs_c="NM_007294.4:c.68_69delAG",
        hgvs_p="NP_009225.1:p.Glu23ValfsTer17",
        transcript=Transcript(
            accession="NM_007294",
            version="4",
            gene_symbol="BRCA1",
            hgvs_c="NM_007294.4:c.68_69delAG",
            hgvs_p="NP_009225.1:p.Glu23ValfsTer17",
            consequence="frameshift_variant",
            mane_select=True,
            canonical=True,
        ),
    )


def _context(**updates) -> GeneDiseaseContext:
    payload = {
        "gene": "BRCA1",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant",
        "lof_is_known_mechanism": True,
        "transcript_is_biologically_relevant": True,
        "nmd_prediction_available": True,
        "nmd_predicted": True,
        "last_exon_information": {"is_in_last_exon": False, "exon_number": 2, "total_exons": 24},
    }
    payload.update(updates)
    return GeneDiseaseContext.model_validate(payload)


def _annotation(**updates) -> VariantAnnotation:
    raw = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "consequence": "frameshift_variant",
    }
    raw.update(updates)
    return VariantAnnotation(
        gene=raw.get("gene"),
        transcript=raw.get("transcript"),
        hgvs_c=raw.get("hgvs_c", "NM_007294.4:c.68_69delAG"),
        hgvs_p=raw.get("hgvs_p", "NP_009225.1:p.Glu23ValfsTer17"),
        consequence=raw.get("consequence"),
        consequence_terms=[raw.get("consequence")] if raw.get("consequence") else [],
        exon=raw.get("exon", "2/24"),
        canonical=raw.get("canonical", True),
        mane_select=raw.get("mane_select", True),
        transcript_biotype=raw.get("transcript_biotype", "protein_coding"),
        annotation_source="pytest",
        provenance=provenance_from_raw_record(
            data_source="pytest",
            source_version="v1",
            query={"case": "pvs1"},
            raw_record=raw,
        ),
        raw_fields=raw,
    )


def test_brca1_frameshift_with_full_context_applies_pvs1() -> None:
    item, decision = generate_pvs1_evidence(_brca1_variant(), annotation=_annotation(), gene_disease_context=_context())

    assert item is not None
    assert decision.applied is True
    assert decision.strength == "PVS1"
    assert item.applied is True
    assert item.requires_review is True
    assert item.supporting_data["requires_manual_review"] is True


def test_brca1_hgvs_only_is_candidate_only() -> None:
    variant = _brca1_variant()
    variant.transcript = None
    item, decision = generate_pvs1_evidence(variant, gene_disease_context=GeneDiseaseContext(gene="BRCA1", disease="Hereditary breast and ovarian cancer syndrome"))

    assert item is not None
    assert decision.applied is False
    assert item.candidate_only is True
    assert "Transcript relevance is missing, mismatched, non-coding, or ambiguous." in decision.blocking_reasons


def test_lof_mechanism_false_blocks_applied_pvs1() -> None:
    item, decision = generate_pvs1_evidence(_brca1_variant(), annotation=_annotation(), gene_disease_context=_context(lof_is_known_mechanism=False))

    assert item is not None
    assert decision.applied is False
    assert item.candidate_only is True
    assert any("LoF is not confirmed" in reason for reason in decision.blocking_reasons)


def test_missing_disease_context_is_candidate_only() -> None:
    item, decision = generate_pvs1_evidence(_brca1_variant(), annotation=_annotation(), gene_disease_context=GeneDiseaseContext(gene="BRCA1", disease="not provided"))

    assert item is not None
    assert decision.applied is False
    assert any("Disease/inheritance context" in reason for reason in decision.blocking_reasons)


def test_transcript_mismatch_is_candidate_only() -> None:
    item, decision = generate_pvs1_evidence(_brca1_variant(), annotation=_annotation(transcript="NM_000000.1"), gene_disease_context=_context())

    assert item is not None
    assert decision.applied is False
    assert any(flag.code == "TRANSCRIPT_MISMATCH" for flag in decision.review_flags)


def test_multiple_transcript_ambiguity_is_candidate_only() -> None:
    selection = TranscriptSelection(
        selected_transcript="NM_007294.4",
        selected_gene="BRCA1",
        selection_reason="tie",
        selection_confidence=0.6,
        candidate_transcripts=[{"transcript": "NM_007294.4"}, {"transcript": "NM_007299.4"}],
        user_transcript_provided=False,
    )

    item, decision = generate_pvs1_evidence(_brca1_variant(), annotation=_annotation(), transcript_selection=selection, gene_disease_context=_context(transcript_is_biologically_relevant=None))

    assert item is not None
    assert decision.applied is False
    assert any(flag.code == "MULTIPLE_TRANSCRIPT_AMBIGUITY" for flag in decision.review_flags)


def test_last_exon_nonsense_is_downgraded() -> None:
    variant = _brca1_variant()
    variant.hgvs_p = "NP_009225.1:p.Gln1800Ter"
    variant.transcript.consequence = "stop_gained"
    item, decision = generate_pvs1_evidence(
        variant,
        annotation=_annotation(consequence="stop_gained", exon="24/24"),
        gene_disease_context=_context(nmd_prediction_available=True, nmd_predicted=False, last_exon_information=LastExonInformation(is_in_last_exon=True, exon_number=24, total_exons=24).model_dump()),
    )

    assert item is not None
    assert decision.applied is True
    assert decision.strength == "PVS1_Supporting"
    assert any("NMD escape" in reason or "terminal" in reason for reason in decision.downgrade_reasons)


def test_nmd_unknown_is_candidate_only() -> None:
    item, decision = generate_pvs1_evidence(
        _brca1_variant(),
        annotation=_annotation(exon=None),
        gene_disease_context=_context(nmd_prediction_available=False, nmd_predicted=None, last_exon_information=None),
    )

    assert item is not None
    assert decision.applied is False
    assert decision.strength == "PVS1_candidate"
    assert item.candidate_only is True
    assert "NMD likelihood is unknown because exon/NMD context is incomplete." in decision.blocking_reasons


def test_start_lost_and_stop_lost_are_candidate_only() -> None:
    start_variant = _brca1_variant()
    start_variant.hgvs_p = "NP_009225.1:p.Met1?"
    start_variant.transcript.consequence = "start_lost"
    start_item, start_decision = generate_pvs1_evidence(start_variant, annotation=_annotation(consequence="start_lost"), gene_disease_context=_context())

    stop_variant = _brca1_variant()
    stop_variant.transcript.consequence = "stop_lost"
    stop_item, stop_decision = generate_pvs1_evidence(stop_variant, annotation=_annotation(consequence="stop_lost"), gene_disease_context=_context())

    assert start_item is not None and start_item.candidate_only is True
    assert stop_item is not None and stop_item.candidate_only is True
    assert start_decision.applied is False
    assert stop_decision.applied is False


def test_canonical_splice_without_rna_is_not_very_strong() -> None:
    variant = _brca1_variant()
    variant.hgvs_c = "NM_007294.4:c.80+1G>T"
    variant.hgvs_p = None
    variant.transcript.consequence = "splice_donor_variant"
    item, decision = generate_pvs1_evidence(variant, annotation=_annotation(consequence="splice_donor_variant"), gene_disease_context=_context())

    assert item is not None
    assert decision.applied is False
    assert decision.strength == "PVS1_candidate"
    assert any(flag.code == "SPLICE_CONSEQUENCE_UNCERTAIN" for flag in decision.review_flags)


def test_splice_predicted_inframe_exon_skipping_is_candidate_only() -> None:
    variant = _brca1_variant()
    variant.hgvs_c = "NM_007294.4:c.80+1G>T"
    variant.hgvs_p = None
    variant.transcript.consequence = "splice_donor_variant"
    item, decision = generate_pvs1_evidence(
        variant,
        annotation=_annotation(consequence="splice_donor_variant"),
        gene_disease_context=_context(),
        provider_data={"inframe_exon_skipping": True},
    )

    assert item is not None
    assert decision.applied is False
    assert any(flag.code == "SPLICE_INFRAME_RESCUE_POSSIBLE" for flag in decision.review_flags)


def test_possible_inframe_rescue_is_candidate_only() -> None:
    variant = _brca1_variant()
    item, decision = generate_pvs1_evidence(
        variant,
        annotation=_annotation(consequence="frameshift_variant"),
        gene_disease_context=_context(),
        provider_data={"possible_inframe_rescue": True},
    )

    assert item is not None
    assert decision.applied is False
    assert any(flag.code == "POSSIBLE_IN_FRAME_RESCUE" for flag in decision.review_flags)


def test_applied_pvs1_changes_classification_only_through_combiner() -> None:
    variant = _brca1_variant()
    context = _context()
    item, _ = generate_pvs1_evidence(variant, annotation=_annotation(), gene_disease_context=context)
    pm2 = EvidenceItem(
        evidence_id="ev-pm2-fixture",
        code="PM2",
        strength=EvidenceStrength.MODERATE,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Fixture PM2 evidence to exercise the existing combiner.",
        source=EvidenceSource(name="pytest", version="v1"),
        confidence=0.8,
        requires_review=True,
    )

    classification = classify_acmg([item, pm2], variant, context)

    assert item is not None
    assert classification.final_classification != "vus"
    assert classification.applied_combination_rule != "default_vus"


def test_candidate_pvs1_does_not_change_classification() -> None:
    variant = _brca1_variant()
    context = _context()
    item, _ = generate_pvs1_evidence(variant, annotation=_annotation(), gene_disease_context=context, provider_data={"possible_inframe_rescue": True})
    pm2 = EvidenceItem(
        evidence_id="ev-pm2-fixture",
        code="PM2",
        strength=EvidenceStrength.MODERATE,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Fixture PM2 evidence.",
        source=EvidenceSource(name="pytest", version="v1"),
        confidence=0.8,
        requires_review=True,
    )

    classification = classify_acmg([item, pm2], variant, context)

    assert item is not None
    assert item.candidate_only is True
    assert classification.final_classification == "vus"


def test_report_includes_pvs1_decision_path_and_downgrades() -> None:
    result = rate_variant(
        {
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
                "annotations": [_annotation().model_dump(mode="json")],
                "pvs1_manual_overrides": {"lof_is_known_mechanism": True},
                "gene_disease_context": _context().model_dump(mode="json"),
            },
        }
    )

    assert result["status"] == "ok"
    assert "PVS1 decision path" in result["report_text"]
    assert result["step_results"]["evaluate_pvs1"]["decision"]["decision_path"]
