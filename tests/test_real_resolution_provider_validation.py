from __future__ import annotations

import json
from pathlib import Path

from variant_pathogenicity_rater.normalization import normalize_variant
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.variant_resolution import resolve_variant


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "transcript_resolution" / "real_resolution_provider_validation.jsonl"


EXPECTED_CASES = {
    "BRCA1": {
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "transcript": "NM_007294.4",
        "protein": "NP_009225.1:p.Glu23ValfsTer17",
        "chrom": "17",
        "pos": 43124027,
        "ref": "CA",
        "alt": "C",
        "exon": 2,
        "total_exons": 24,
        "nmd": "NMD_expected",
    },
    "CFTR": {
        "hgvs_c": "NM_000492.4:c.1521_1523delCTT",
        "transcript": "NM_000492.4",
        "protein": "NP_000483.3:p.Phe508del",
        "chrom": "7",
        "pos": 117559590,
        "ref": "CTTT",
        "alt": "T",
        "exon": 11,
        "total_exons": 27,
        "nmd": "NMD_unlikely",
    },
    "GJB2": {
        "hgvs_c": "NM_004004.6:c.235delC",
        "transcript": "NM_004004.6",
        "protein": "NP_003995.2:p.Leu79CysfsTer3",
        "chrom": "13",
        "pos": 20763686,
        "ref": "CC",
        "alt": "C",
        "exon": 2,
        "total_exons": 2,
        "nmd": "NMD_unlikely",
    },
    "DMD": {
        "hgvs_c": "NM_004006.3:c.7318C>T",
        "transcript": "NM_004006.3",
        "protein": "NP_003997.2:p.Arg2440Ter",
        "chrom": "X",
        "pos": 32387779,
        "ref": "G",
        "alt": "A",
        "exon": 51,
        "total_exons": 79,
        "nmd": "NMD_expected",
    },
    "PAH": {
        "hgvs_c": "NM_000277.3:c.1222C>T",
        "transcript": "NM_000277.3",
        "protein": "NP_000268.1:p.Arg408Trp",
        "chrom": "12",
        "pos": 102838887,
        "ref": "C",
        "alt": "T",
        "exon": 12,
        "total_exons": 13,
        "nmd": "NMD_unlikely",
    },
    "TP53": {
        "hgvs_c": "NM_000546.6:c.743G>A",
        "transcript": "NM_000546.6",
        "protein": "NP_000537.3:p.Arg248Gln",
        "chrom": "17",
        "pos": 7674221,
        "ref": "G",
        "alt": "A",
        "exon": 7,
        "total_exons": 11,
        "nmd": "NMD_unlikely",
    },
}


def _records() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


def _normalized(gene: str, hgvs_c: str, **extra: object):
    result = normalize_variant({"gene": gene, "hgvs_c": hgvs_c, **extra})
    assert result.normalized_variant is not None
    return result.normalized_variant


def _rate_payload(gene: str, hgvs_c: str, records: list[dict] | str | None) -> dict:
    return {
        "gene": gene,
        "hgvs_c": hgvs_c,
        "disease": "Resolution validation condition",
        "inheritance": "autosomal_dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "transcript_resolution_records": records,
            "gene_disease_context": {
                "gene": gene,
                "disease": "Resolution validation condition",
                "inheritance": "autosomal_dominant",
            },
        },
    }


def test_real_resolution_snapshot_preserves_required_fields() -> None:
    required = {
        "gene",
        "transcript",
        "hgvs_c",
        "protein_accession",
        "hgvs_p",
        "consequence",
        "genome_build",
        "chrom",
        "pos",
        "ref",
        "alt",
        "exon_number",
        "total_exons",
        "source",
        "source_version",
        "raw_snapshot_ref",
        "provenance",
    }

    records = _records()

    assert len(records) == 6
    assert all(required.issubset(record) for record in records)
    assert all(record["source_version"] == "real-resolution-provider-validation-2026-06" for record in records)
    assert all(record["provenance"]["scope"] == "variant resolution only; not ACMG evidence" for record in records)


def test_all_named_variants_resolve_transcript_protein_coordinate_exon_and_nmd_from_snapshot_path() -> None:
    for gene, expected in EXPECTED_CASES.items():
        variant = _normalized(gene, expected["hgvs_c"])

        result = resolve_variant(variant, options={"transcript_resolution_records": str(FIXTURE)})

        assert result.status == "resolved"
        assert result.resolved_transcript.transcript == expected["transcript"]
        assert result.resolved_hgvs_p.hgvs_p == expected["protein"]
        assert result.resolved_coordinate.chrom == expected["chrom"]
        assert result.resolved_coordinate.pos == expected["pos"]
        assert result.resolved_coordinate.ref == expected["ref"]
        assert result.resolved_coordinate.alt == expected["alt"]
        assert result.exon_context.exon_number == expected["exon"]
        assert result.exon_context.total_exons == expected["total_exons"]
        assert result.nmd_context.status == expected["nmd"]
        flag_codes = {flag.code for flag in result.review_flags}
        assert "RESOLUTION_BUILD_MISMATCH" not in flag_codes
        assert "RESOLUTION_TRANSCRIPT_MISMATCH" not in flag_codes
        assert "RESOLUTION_TRANSCRIPT_VERSION_MISMATCH" not in flag_codes


def test_inline_records_resolve_without_default_network_or_provider_calls() -> None:
    expected = EXPECTED_CASES["TP53"]
    variant = _normalized("TP53", expected["hgvs_c"])

    result = resolve_variant(variant, records=_records())

    assert result.status == "resolved"
    assert result.resolved_transcript.transcript == expected["transcript"]
    assert result.resolved_hgvs_p.hgvs_p == expected["protein"]
    assert result.provenance[0]["source"] == "local_real_resolution_provider_snapshot"
    assert result.provenance[0]["scope"] == "variant resolution only; not ACMG evidence"


def test_malformed_provider_snapshot_becomes_limitation() -> None:
    variant = _normalized("TP53", EXPECTED_CASES["TP53"]["hgvs_c"])

    result = resolve_variant(variant, records="not-json")

    assert result.status in {"partial", "unresolved"}
    assert any("Malformed transcript resolution JSONL line" in limitation for limitation in result.limitations)
    assert result.review_flags == []


def test_missing_mapping_becomes_limitation_only() -> None:
    variant = _normalized("BRCA2", "NM_000059.4:c.5946delT")

    result = resolve_variant(variant, records=_records())

    assert result.status in {"partial", "unresolved"}
    assert any("No matching local transcript resolution fixture was found" in item for item in result.limitations)
    assert result.review_flags == []


def test_build_mismatch_creates_review_flag_and_preserves_input_coordinate() -> None:
    expected = EXPECTED_CASES["TP53"]
    variant = _normalized(
        "TP53",
        expected["hgvs_c"],
        genome_build="GRCh37",
        chromosome="17",
        position=7577548,
        ref="G",
        alt="A",
    )

    result = resolve_variant(variant, records=_records())

    assert {flag.code for flag in result.review_flags} == {"RESOLUTION_BUILD_MISMATCH", "RESOLUTION_COORDINATE_CONFLICT"}
    assert result.resolved_variant.genome_build == "GRCh37"
    assert result.resolved_variant.chrom == "17"
    assert result.resolved_variant.pos == 7577548


def test_transcript_accession_and_version_mismatches_create_review_flags() -> None:
    expected = EXPECTED_CASES["TP53"]
    accession_mismatch = _normalized("TP53", expected["hgvs_c"], transcript="NM_001126112.2")
    version_mismatch = _normalized("TP53", expected["hgvs_c"], transcript="NM_000546.5")

    accession_result = resolve_variant(accession_mismatch, records=_records())
    version_result = resolve_variant(version_mismatch, records=_records())

    assert {flag.code for flag in accession_result.review_flags} == {"RESOLUTION_TRANSCRIPT_MISMATCH"}
    assert {flag.code for flag in version_result.review_flags} == {"RESOLUTION_TRANSCRIPT_VERSION_MISMATCH"}
    assert accession_result.resolved_variant.transcript.accession == "NM_001126112"
    assert version_result.resolved_variant.transcript.version == "5"


def test_resolution_does_not_change_classification_or_create_evidence_items() -> None:
    expected = EXPECTED_CASES["TP53"]

    unresolved = rate_variant(_rate_payload("TP53", expected["hgvs_c"], []))
    resolved = rate_variant(_rate_payload("TP53", expected["hgvs_c"], _records()))

    assert unresolved["final_classification"] == resolved["final_classification"] == "vus"
    assert unresolved["variant_resolution"]["status"] in {"partial", "unresolved"}
    assert resolved["variant_resolution"]["status"] == "resolved"
    assert unresolved["evidence_items"] == []
    assert resolved["evidence_items"] == []
    assert resolved["applied_evidence"] == []
    assert resolved["step_results"]["combine_all_evidence"]["evidence_item_count"] == 0


def test_resolution_failure_does_not_generate_resolution_derived_acmg_codes() -> None:
    result = rate_variant(_rate_payload("NOPE", "NM_000000.1:c.1A>G", []))

    assert result["variant_resolution"]["status"] in {"partial", "unresolved"}
    assert result["evidence_items"] == []
    assert result["applied_evidence"] == []
    assert result["step_results"]["combine_all_evidence"]["evidence_ids"] == []
    assert any("No matching local transcript resolution fixture was found" in item for item in result["limitations"])
