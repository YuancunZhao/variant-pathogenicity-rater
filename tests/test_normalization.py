from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.annotation import OnlineResolverConfig, OnlineVariantNormalizer
from variant_pathogenicity_rater.normalization import NormalizationError, normalize_variant
from variant_pathogenicity_rater.schemas import GeneDiseaseContext


ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))


def test_normalize_vcf_like_snv() -> None:
    result = normalize_variant(
        {
            "input_type": "vcf_like",
            "chrom": "7",
            "pos": 140453136,
            "ref": "A",
            "alt": "T",
            "genome_build": "GRCh38",
        }
    )

    assert result.status == "normalized"
    assert result.normalized_variant is not None
    assert result.normalized_variant.variant_type == "snv"
    assert result.normalized_variant.variant_id == "GRCh38-7-140453136-A-T"
    assert result.unresolved_fields == []
    assert result.human_review_required is True
    assert result.variant_identity is not None
    assert result.variant_identity.genomic_key == "7-140453136-A-T"
    assert result.variant_identity.normalized_variant_key == "7-140453136-A-T"
    assert result.variant_identity.input_hash
    assert result.variant_identity.provenance


def test_normalize_vcf_like_small_deletion_preserves_transcript() -> None:
    result = normalize_variant(
        {
            "chromosome": "13",
            "position": 32316461,
            "ref": "AT",
            "alt": "A",
            "gene_symbol": "BRCA2",
            "transcript": "NM_000059.4",
            "hgvs_c": "NM_000059.4:c.5946delT",
            "hgvs_p": "NP_000050.3:p.Ser1982ArgfsTer22",
            "genome_build": "GRCh38",
        }
    )

    variant = result.normalized_variant
    assert variant is not None
    assert variant.variant_type == "small_deletion"
    assert variant.transcript is not None
    assert variant.transcript.accession == "NM_000059"
    assert variant.transcript.version == "4"
    assert variant.hgvs_c == "NM_000059.4:c.5946delT"


def test_normalize_hgvs_like_snv_preserves_unresolved_genomic_fields() -> None:
    result = normalize_variant(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68A>G",
            "hgvs_p": "NP_009225.1:p.Lys23Arg",
        }
    )

    variant = result.normalized_variant
    assert variant is not None
    assert variant.variant_type == "snv"
    assert variant.ref == "A"
    assert variant.alt == "G"
    assert variant.transcript is not None
    assert variant.transcript.accession == "NM_007294"
    assert "chrom" in result.unresolved_fields
    assert "pos" in result.unresolved_fields
    assert any("external normalization" in warning for warning in result.normalization_warnings)


def test_missing_transcript_and_hgvs_p_are_warnings() -> None:
    result = normalize_variant({"hgvs_c": "c.76A>G", "gene_symbol": "GENE1"})

    assert result.status == "normalized"
    assert {"transcript", "hgvs_p", "chrom", "pos"}.issubset(set(result.unresolved_fields))
    assert len(result.normalization_warnings) >= 4


def test_multiallelic_input_is_rejected() -> None:
    with pytest.raises(NormalizationError, match="Multi-allelic"):
        normalize_variant({"chrom": "1", "pos": 10, "ref": "A", "alt": "C,G"})


def test_insertion_deletion_trimming_and_chr_prefix_normalization() -> None:
    result = normalize_variant({"chrom": "chr13", "pos": 100, "ref": "CAT", "alt": "CA"})

    variant = result.normalized_variant
    assert variant is not None
    assert variant.chrom == "13"
    assert variant.pos == 101
    assert variant.ref == "AT"
    assert variant.alt == "A"
    assert result.variant_identity is not None
    assert result.variant_identity.genomic_key == "13-101-AT-A"
    assert any("trimmed" in warning for warning in result.normalization_warnings)


def test_hgvs_genomic_conflict_is_review_flag() -> None:
    result = normalize_variant(
        {
            "chrom": "1",
            "pos": 10,
            "ref": "A",
            "alt": "G",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.10A>T",
            "gene_symbol": "GENE1",
        }
    )

    assert "HGVS_GENOMIC_MISMATCH" in {flag.code for flag in result.review_flags}


def test_user_transcript_is_preserved_when_hgvs_differs() -> None:
    result = normalize_variant(
        {
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000002.1:c.10A>G",
            "gene_symbol": "GENE1",
        }
    )

    variant = result.normalized_variant
    assert variant is not None
    assert variant.transcript is not None
    assert variant.transcript.accession == "NM_000001"
    assert "TRANSCRIPT_MISMATCH" in {flag.code for flag in result.review_flags}


def test_online_normalizer_disabled_by_default() -> None:
    result = normalize_variant({"chrom": "1", "pos": 10, "ref": "A", "alt": "G"})

    assert any("disabled by default" in limitation for limitation in result.limitations)
    assert any(item["source"] == "online_variant_normalizer" for item in result.provenance)


def test_mocked_online_normalizer_success_and_failure(tmp_path) -> None:
    def fetcher(_query: dict[str, object], _timeout_seconds: float) -> dict[str, object]:
        return {
            "confidence": 0.95,
            "normalized_variant": {"chrom": "1", "pos": 10, "ref": "A", "alt": "G"},
        }

    resolver = OnlineVariantNormalizer(
        OnlineResolverConfig(
            name="normalizer",
            enabled=True,
            online_enabled=True,
            cache_dir=str(tmp_path / "cache"),
        ),
        fetcher=fetcher,
    )
    success = normalize_variant(
        {"chrom": "1", "pos": 10, "ref": "A", "alt": "G"},
        online_normalizer=resolver,
    )

    assert "ONLINE_NORMALIZER_CONFLICT" not in {flag.code for flag in success.review_flags}
    assert any(item.get("status") == "confirmed_high_confidence" for item in success.provenance)

    def failing_fetcher(_query: dict[str, object], _timeout_seconds: float) -> dict[str, object]:
        raise TimeoutError("offline test timeout")

    failing_resolver = OnlineVariantNormalizer(
        OnlineResolverConfig(
            name="normalizer",
            enabled=True,
            online_enabled=True,
            cache_dir=str(tmp_path / "failing-cache"),
        ),
        fetcher=failing_fetcher,
    )
    failure = normalize_variant(
        {"chrom": "1", "pos": 10, "ref": "A", "alt": "G"},
        online_normalizer=failing_resolver,
    )

    assert failure.status == "normalized"
    assert any("TimeoutError" in limitation for limitation in failure.limitations)


def test_normalization_does_not_change_classification() -> None:
    raw = {"chrom": "chr1", "pos": 10, "ref": "A", "alt": "G", "gene_symbol": "GENE1"}
    normalized = normalize_variant(raw).normalized_variant
    assert normalized is not None

    context = GeneDiseaseContext(gene_symbol="GENE1", disease_name="Example disease")
    before = classify_acmg([], normalized, context)
    after = classify_acmg([], normalized, context)

    assert before.final_classification == after.final_classification == "vus"


def test_invalid_ref_alt_is_rejected() -> None:
    with pytest.raises(NormalizationError, match="must contain only"):
        normalize_variant({"chrom": "1", "pos": 10, "ref": "A", "alt": "<DEL>"})


def test_malformed_hgvs_is_schema_validation_error() -> None:
    with pytest.raises(NormalizationError) as exc_info:
        normalize_variant({"gene": "GENE1", "transcript": "NM_000001.1", "hgvs_c": "c.76A"})

    assert exc_info.value.code == "SCHEMA_VALIDATION_ERROR"
    assert exc_info.value.unresolved_fields == ["hgvs_c"]


def test_unsupported_sv_hgvs_input_is_rejected() -> None:
    with pytest.raises(NormalizationError) as exc_info:
        normalize_variant({"gene": "GENE1", "transcript": "NM_000001.1", "hgvs_c": "c.123_456inv"})

    assert exc_info.value.code == "UNSUPPORTED_VARIANT_TYPE"


def test_large_indel_is_rejected_as_out_of_scope() -> None:
    with pytest.raises(NormalizationError, match="small indel"):
        normalize_variant({"chrom": "1", "pos": 10, "ref": "A", "alt": "A" * 51})


def test_mcp_normalize_variant_tool_returns_standard_payload() -> None:
    from tools.rate_variant import normalize_variant as normalize_variant_tool

    payload = asyncio.run(
        normalize_variant_tool(
            {
                "variant": {
                    "input_type": "vcf_like",
                    "chrom": "1",
                    "pos": 123,
                    "ref": "G",
                    "alt": "A",
                }
            }
        )
    )

    assert payload["status"] == "normalized"
    assert payload["tool"] == "normalize_variant"
    assert payload["normalized_variant"]["variant_type"] == "snv"
    assert payload["human_review_required"] is True


def test_chr_m_and_mt_normalize_to_same_identity() -> None:
    chr_m = normalize_variant({"chrom": "chrM", "pos": 10, "ref": "A", "alt": "G"})
    mt = normalize_variant({"chrom": "MT", "pos": 10, "ref": "A", "alt": "G"})

    assert chr_m.normalized_variant is not None
    assert mt.normalized_variant is not None
    assert chr_m.normalized_variant.chrom == "MT"
    assert chr_m.variant_identity is not None
    assert mt.variant_identity is not None
    assert chr_m.variant_identity.normalized_variant_key == mt.variant_identity.normalized_variant_key


def test_lowercase_ref_alt_and_spaced_gene_transcript_are_cleaned_with_warnings() -> None:
    result = normalize_variant(
        {
            "chrom": "chr17",
            "pos": "43092919",
            "ref": " a ",
            "alt": " g ",
            "gene": " brca1 ",
            "transcript": " nm_007294.4 ",
            "hgvs_c": "NM_007294.4:c.68A>G",
        }
    )

    variant = result.normalized_variant
    assert variant is not None
    assert variant.ref == "A"
    assert variant.alt == "G"
    assert variant.gene_symbol == "BRCA1"
    assert variant.transcript is not None
    assert variant.transcript.accession == "NM_007294"
    assert any("uppercased" in warning for warning in result.normalization_warnings)


def test_url_and_html_escaped_hgvs_is_cleaned() -> None:
    result = normalize_variant(
        {
            "gene": "GENE1",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.76A%3EG",
            "hgvs_p": "NP_000001.1:p.Lys26Arg&amp;",
        }
    )

    variant = result.normalized_variant
    assert variant is not None
    assert variant.hgvs_c == "NM_000001.1:c.76A>G"
    assert any("URL/HTML-decoded" in warning for warning in result.normalization_warnings)


def test_dot_symbolic_n_and_multiallelic_alt_are_rejected_safely() -> None:
    for alt in [".", "<DEL>", "N", "G,T"]:
        with pytest.raises(NormalizationError):
            normalize_variant({"chrom": "1", "pos": 10, "ref": "A", "alt": alt})
