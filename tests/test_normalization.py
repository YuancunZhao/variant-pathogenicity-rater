from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from variant_pathogenicity_rater.normalization import NormalizationError, normalize_variant


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
