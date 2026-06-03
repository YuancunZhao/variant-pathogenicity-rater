from __future__ import annotations

from variant_pathogenicity_rater.normalization import normalize_variant
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext
from variant_pathogenicity_rater.variant_resolution import resolve_variant


def _normalized(payload: dict):
    result = normalize_variant(payload)
    assert result.normalized_variant is not None
    return result.normalized_variant


def test_brca1_hgvs_c_resolves_transcript_protein_coordinate_exon_and_nmd() -> None:
    variant = _normalized({"gene": "BRCA1", "hgvs_c": "NM_007294.4:c.68_69delAG"})

    result = resolve_variant(variant)

    assert result.status == "resolved"
    assert result.resolved_transcript.transcript == "NM_007294.4"
    assert result.resolved_hgvs_p.hgvs_p == "NP_009225.1:p.Glu23ValfsTer17"
    assert result.resolved_coordinate.chrom == "17"
    assert result.resolved_coordinate.pos == 43124027
    assert result.resolved_coordinate.ref == "CA"
    assert result.resolved_coordinate.alt == "C"
    assert result.exon_context.exon_number == 2
    assert result.exon_context.total_exons == 24
    assert result.nmd_context.status == "NMD_expected"
    assert result.resolved_variant.hgvs_p == "NP_009225.1:p.Glu23ValfsTer17"


def test_transcript_absent_returns_mane_suggestion_only() -> None:
    variant = _normalized({"gene": "BRCA1", "hgvs_c": "c.68_69delAG"})

    result = resolve_variant(variant)

    assert result.resolved_transcript.transcript == "NM_007294.4"
    assert result.resolved_transcript.suggestion_only is True
    assert result.resolved_transcript.transcript_source == "mane_select_recommendation"
    assert result.resolved_variant.transcript is None


def test_user_transcript_is_not_overridden_by_resolution() -> None:
    variant = _normalized(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68_69delAG",
        }
    )

    result = resolve_variant(variant)

    assert result.resolved_transcript.user_transcript_provided is True
    assert result.resolved_transcript.user_transcript_preserved is True
    assert result.resolved_variant.transcript.accession == "NM_007294"
    assert result.resolved_variant.transcript.version == "4"


def test_coordinate_unavailable_is_limitation_only() -> None:
    variant = _normalized({"gene": "BRCA2", "hgvs_c": "NM_000059.4:c.5946delT"})

    result = resolve_variant(variant)

    assert result.status in {"partial", "unresolved"}
    assert result.resolved_coordinate.confidence == 0.0
    assert any("coordinate" in limitation.lower() for limitation in result.limitations)
    assert result.review_flags == []


def test_early_frameshift_derives_nmd_expected_from_fixture() -> None:
    variant = _normalized({"gene": "BRCA1", "hgvs_c": "NM_007294.4:c.68_69delAG"})

    result = resolve_variant(variant)

    assert result.exon_context.last_exon is False
    assert result.nmd_context.status == "NMD_expected"
    assert result.resolved_context is None


def test_last_exon_frameshift_derives_nmd_unlikely_from_inline_fixture() -> None:
    variant = _normalized({"gene": "GENE1", "hgvs_c": "NM_000001.1:c.900delA"})
    records = [
        {
            "gene": "GENE1",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.900delA",
            "protein_accession": "NP_000001.1",
            "hgvs_p": "NP_000001.1:p.Lys300ArgfsTer2",
            "consequence": "frameshift_variant",
            "genome_build": "GRCh38",
            "chrom": "1",
            "pos": 1000,
            "ref": "AA",
            "alt": "A",
            "exon_number": 10,
            "total_exons": 10,
            "confidence": 0.9,
        }
    ]

    result = resolve_variant(variant, records=records)

    assert result.exon_context.last_exon is True
    assert result.nmd_context.status == "NMD_unlikely"


def test_resolution_improves_pvs1_inputs_without_changing_combiner_boundary() -> None:
    payload = {
        "gene": "BRCA1",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "gene_disease_context": {
                "gene": "BRCA1",
                "disease": "Hereditary breast and ovarian cancer syndrome",
                "inheritance": "autosomal_dominant",
                "lof_is_known_mechanism": True,
                "transcript_is_biologically_relevant": True,
            },
        },
    }

    result = rate_variant(payload)

    assert result["variant_resolution"]["resolved_hgvs_p"]["hgvs_p"] == "NP_009225.1:p.Glu23ValfsTer17"
    assert result["step_results"]["resolve_variant"]["nmd_context"]["status"] == "NMD_expected"
    assert result["step_results"]["evaluate_pvs1"]["decision"]["nmd"]["nmd_likely"] is True
    assert "classify_acmg" in result["step_results"]
    assert result["classification_result"]["human_review_required"] is True
