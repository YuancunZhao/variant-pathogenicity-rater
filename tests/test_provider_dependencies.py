from __future__ import annotations

import importlib

import pytest

from variant_pathogenicity_rater.providers import (
    ProviderDependencyStatus,
    VariantIdentity,
    check_clinvar_dependency,
    check_gnomad_dependency,
    check_literature_dependency,
    check_vep_dependency,
)

RATE_VARIANT_MODULE = importlib.import_module("variant_pathogenicity_rater.pipeline.rate_variant")


def test_gnomad_valid_identity_is_satisfied() -> None:
    check = check_gnomad_dependency(
        VariantIdentity(
            gene="GENE1",
            genome_build="GRCh38",
            chrom="chr1",
            pos=100,
            ref="A",
            alt="G",
        )
    )

    assert check.satisfied is True
    assert check.status == ProviderDependencyStatus.SATISFIED
    assert check.identity_snapshot["gnomad_variant_id"] == "1-100-A-G"


def test_gnomad_missing_coordinate_is_skipped() -> None:
    check = check_gnomad_dependency(
        VariantIdentity(gene="GENE1", genome_build="GRCh38", chrom="1", ref="A", alt="G")
    )

    assert check.satisfied is False
    assert check.status == ProviderDependencyStatus.MISSING_IDENTITY
    assert "skipped is not no_record" in " ".join(check.limitations)


def test_gnomad_placeholder_ref_alt_is_skipped() -> None:
    check = check_gnomad_dependency(
        VariantIdentity(
            gene="GENE1",
            genome_build="GRCh38",
            chrom="1",
            pos=100,
            ref="N",
            alt="unresolved",
        )
    )

    assert check.satisfied is False
    assert check.status == ProviderDependencyStatus.INVALID_IDENTITY
    assert check.review_flags[0].code == "PROVIDER_DEPENDENCY_GNOMAD_INVALID_IDENTITY"


def test_gnomad_invalid_variant_id_grammar_is_skipped() -> None:
    check = check_gnomad_dependency(
        VariantIdentity(
            gene="GENE1",
            genome_build="GRCh38",
            chrom="1",
            pos=100,
            ref="R",
            alt="G",
        )
    )

    assert check.satisfied is False
    assert check.status == ProviderDependencyStatus.INVALID_IDENTITY
    assert "failed basic grammar" in " ".join(check.limitations)


def test_vep_coordinate_missing_but_hgvs_present_is_satisfied() -> None:
    check = check_vep_dependency(
        VariantIdentity(gene="GENE1", transcript="NM_000001.1", hgvs_c="NM_000001.1:c.1A>G")
    )

    assert check.satisfied is True


def test_vep_no_coordinate_and_no_hgvs_is_skipped() -> None:
    check = check_vep_dependency(VariantIdentity(gene="GENE1"))

    assert check.satisfied is False
    assert check.status == ProviderDependencyStatus.MISSING_IDENTITY


def test_clinvar_alias_present_is_satisfied() -> None:
    check = check_clinvar_dependency(
        VariantIdentity(gene="GENE1", transcript="NM_000001.1", hgvs_c="NM_000001.1:c.1A>G")
    )

    assert check.satisfied is True


def test_literature_gene_present_is_satisfied() -> None:
    check = check_literature_dependency(VariantIdentity(gene="GENE1"))

    assert check.satisfied is True


def test_online_gnomad_dependency_skip_does_not_call_provider_or_produce_pm2(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_build_population_provider(*_args, **_kwargs):
        raise AssertionError("population provider should not be constructed when gnomAD identity is invalid")

    monkeypatch.setattr(RATE_VARIANT_MODULE, "build_population_provider", fail_build_population_provider)

    result = RATE_VARIANT_MODULE.rate_variant(
        {
            "gene": "GENE1",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.1A>G",
            "disease": "not provided",
            "options": {
                "mock_mode": True,
                "use_online_gnomad": True,
                "include_computational": False,
                "include_clinvar": False,
                "include_literature": False,
            },
        }
    )

    population_runtime = result["step_results"]["provider_runtime"]["population"]
    assert population_runtime["outcome"] == "skipped"
    assert population_runtime["attempted"] is False
    assert population_runtime["dependency_status"]["status"] == "invalid_identity"
    assert result["provider_mode_summary"]["population"]["actual_outcome"] == "skipped"
    assert "query_population_frequency" in result["step_results"]
    assert result["step_results"]["query_population_frequency"]["provider_dependency"]["satisfied"] is False
    assert all(item["code"] != "PM2" for item in result["applied_evidence"])
    assert result["final_classification"] == result["classification_result"]["final_classification"]
