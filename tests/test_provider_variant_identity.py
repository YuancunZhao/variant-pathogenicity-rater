from __future__ import annotations

from variant_pathogenicity_rater.normalization import normalize_variant
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.providers import (
    VariantIdentity,
    build_gnomad_variant_id,
    build_variant_identity,
    identity_aliases_for_clinvar,
    identity_aliases_for_literature,
    identity_aliases_for_vep,
    merge_variant_identities,
    validate_gnomad_variant_id,
    variant_identity_from_normalized_variant,
    variant_identity_from_resolution,
)
from variant_pathogenicity_rater.variant_resolution import resolve_variant


def _normalized_brca1():
    result = normalize_variant(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68_69delAG",
            "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
            "genome_build": "GRCh38",
            "chrom": "17",
            "pos": 43124027,
            "ref": "CA",
            "alt": "C",
        }
    )
    assert result.normalized_variant is not None
    return result.normalized_variant


def test_provider_identity_from_normalized_structured_coordinate() -> None:
    identity = variant_identity_from_normalized_variant(_normalized_brca1())

    assert identity.gene == "BRCA1"
    assert identity.transcript == "NM_007294.4"
    assert identity.hgvs_c == "NM_007294.4:c.68_69delAG"
    assert identity.hgvs_p == "NP_009225.1:p.Glu23ValfsTer17"
    assert identity.genome_build == "GRCh38"
    assert identity.chrom == "17"
    assert identity.pos == 43124027
    assert identity.ref == "CA"
    assert identity.alt == "C"
    assert identity.gnomad_variant_id == "17-43124027-CA-C"
    assert identity.model_dump(mode="json")["gene"] == "BRCA1"


def test_provider_identity_from_variant_resolution_fixture() -> None:
    variant = _normalized_brca1()
    resolution = resolve_variant(variant)

    identity = variant_identity_from_resolution(resolution)

    assert identity.transcript == "NM_007294.4"
    assert identity.hgvs_p == "NP_009225.1:p.Glu23ValfsTer17"
    assert identity.consequence == "frameshift_variant"
    assert identity.chrom == "17"
    assert identity.ref == "CA"
    assert identity.alt == "C"


def test_build_variant_identity_merges_normalized_and_resolution_without_conflict() -> None:
    variant = _normalized_brca1()
    resolution = resolve_variant(variant)

    identity = build_variant_identity(normalized_variant=variant, variant_resolution=resolution)

    assert identity.gnomad_variant_id == "17-43124027-CA-C"
    assert identity.identity_conflicts == []
    assert not any(flag.code.startswith("PROVIDER_IDENTITY") for flag in identity.review_flags)


def test_coordinate_conflict_creates_identity_conflicts_and_review_flags() -> None:
    base = VariantIdentity(
        gene="BRCA1",
        genome_build="GRCh38",
        chrom="17",
        pos=43124027,
        ref="CA",
        alt="C",
        identity_confidence=0.8,
    )
    update = VariantIdentity(
        gene="BRCA1",
        genome_build="GRCh38",
        chrom="17",
        pos=43124028,
        ref="AA",
        alt="A",
        identity_confidence=0.95,
    )

    merged = merge_variant_identities(base, update, source="pytest_resolution")

    assert merged.pos == 43124027
    assert merged.ref == "CA"
    assert merged.alt == "C"
    assert {conflict["field"] for conflict in merged.identity_conflicts} == {"pos", "ref", "alt"}
    assert {flag.code for flag in merged.review_flags} >= {
        "PROVIDER_IDENTITY_POS_CONFLICT",
        "PROVIDER_IDENTITY_REF_CONFLICT",
        "PROVIDER_IDENTITY_ALT_CONFLICT",
    }
    assert any("kept base value" in item for item in merged.limitations)


def test_missing_coordinate_does_not_generate_gnomad_variant_id() -> None:
    identity = validate_gnomad_variant_id(
        VariantIdentity(gene="BRCA1", genome_build="GRCh38", chrom="17", ref="A", alt="G")
    )

    assert identity.gnomad_variant_id is None
    assert any("required identity fields are missing" in item for item in identity.limitations)


def test_placeholder_ref_alt_does_not_generate_gnomad_variant_id() -> None:
    identity = validate_gnomad_variant_id(
        VariantIdentity(
            gene="BRCA1",
            genome_build="GRCh38",
            chrom="17",
            pos=43124027,
            ref="N",
            alt="unresolved",
        )
    )

    assert identity.gnomad_variant_id is None
    assert any("failed basic grammar" in item for item in identity.limitations)


def test_valid_grch38_snv_generates_gnomad_variant_id_and_strips_chr_prefix() -> None:
    identity = validate_gnomad_variant_id(
        VariantIdentity(
            gene="GENE1",
            genome_build="GRCh38",
            chrom="chr1",
            pos=100,
            ref="A",
            alt="G",
        )
    )

    assert identity.chrom == "1"
    assert identity.gnomad_variant_id == "1-100-A-G"
    assert build_gnomad_variant_id(identity) == "1-100-A-G"


def test_clinvar_aliases_include_transcript_hgvs_and_protein() -> None:
    identity = VariantIdentity(
        gene="BRCA1",
        transcript="NM_007294.4",
        hgvs_c="c.68_69delAG",
        hgvs_p="NP_009225.1:p.Glu23ValfsTer17",
        protein_change="p.Glu23ValfsTer17",
        rsid="rs80357713",
        clinvar_variation_id="17661",
    )

    aliases = identity_aliases_for_clinvar(identity)

    assert "NM_007294.4:c.68_69delAG" in aliases
    assert "NP_009225.1:p.Glu23ValfsTer17" in aliases
    assert "p.Glu23ValfsTer17" in aliases
    assert "rs80357713" in aliases
    assert "17661" in aliases


def test_vep_aliases_include_coordinate_and_hgvs() -> None:
    identity = validate_gnomad_variant_id(
        VariantIdentity(
            gene="BRCA1",
            transcript="NM_007294.4",
            hgvs_c="NM_007294.4:c.68_69delAG",
            hgvs_g="NC_000017.11:g.43124027_43124028del",
            genome_build="GRCh38",
            chrom="17",
            pos=43124027,
            ref="CA",
            alt="C",
        )
    )

    aliases = identity_aliases_for_vep(identity)

    assert "NM_007294.4:c.68_69delAG" in aliases
    assert "NC_000017.11:g.43124027_43124028del" in aliases
    assert "GRCh38:17:43124027:CA>C" in aliases
    assert "17-43124027-CA-C" in aliases


def test_literature_aliases_include_gene_hgvs_c_and_hgvs_p() -> None:
    identity = VariantIdentity(
        gene="BRCA1",
        transcript="NM_007294.4",
        hgvs_c="NM_007294.4:c.68_69delAG",
        hgvs_p="NP_009225.1:p.Glu23ValfsTer17",
    )

    aliases = identity_aliases_for_literature(identity)

    assert "BRCA1" in aliases
    assert "NM_007294.4:c.68_69delAG" in aliases
    assert "NP_009225.1:p.Glu23ValfsTer17" in aliases


def test_rate_variant_provider_identity_is_additive_and_does_not_change_evidence() -> None:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43124027,
        "ref": "CA",
        "alt": "C",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }
    base = rate_variant(payload)
    with_alias = rate_variant(
        {
            **payload,
            "options": {
                **payload["options"],
                "provider_identity_aliases": {"rsid": "rs80357713", "identity_confidence": 0.5},
            },
        }
    )

    assert with_alias["provider_identity"]["rsid"] == "rs80357713"
    assert with_alias["variant"]["provider_identity"] == with_alias["provider_identity"]
    assert base["final_classification"] == with_alias["final_classification"]
    assert _stable_evidence(base["evidence_items"]) == _stable_evidence(with_alias["evidence_items"])
    assert _stable_evidence(base["applied_evidence"]) == _stable_evidence(with_alias["applied_evidence"])


def _stable_evidence(items: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "code": item.get("code"),
            "strength": item.get("strength"),
            "direction": item.get("direction"),
            "applied": item.get("applied"),
            "candidate_only": item.get("candidate_only"),
            "evidence_status": item.get("evidence_status"),
        }
        for item in items
    ]
