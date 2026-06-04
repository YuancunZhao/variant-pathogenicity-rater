from __future__ import annotations

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.runtime.options import (
    RuntimeOptions,
    apply_online_provider_modes,
    normalize_runtime_options,
    runtime_options_to_pipeline_dict,
)


def _variant_payload(options: dict | None = None) -> dict:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43092919,
        "ref": "AG",
        "alt": "A",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
    }
    if options is not None:
        payload["options"] = options
    return payload


def _stable_evidence_summary(items: list[dict]) -> list[tuple]:
    return [
        (
            item.get("code"),
            item.get("strength"),
            item.get("direction"),
            item.get("applied"),
            item.get("candidate_only"),
            item.get("requires_review"),
        )
        for item in items
    ]


def test_runtime_options_defaults_preserve_mock_offline_no_online() -> None:
    runtime = normalize_runtime_options()

    assert runtime.mock_mode is True
    assert runtime.use_online_clinvar is False
    assert runtime.use_online_gnomad is False
    assert runtime.use_online_vep is False
    assert runtime.use_online_pubmed is False
    assert runtime.use_online_litvar is False
    assert "data_sources" not in runtime.passthrough_options

    pipeline_options = runtime_options_to_pipeline_dict(runtime)
    assert pipeline_options == {"mock_mode": True}


def test_online_flags_generate_existing_data_sources_mapping(tmp_path) -> None:
    runtime = normalize_runtime_options(
        {
            "use_online_clinvar": True,
            "use_online_gnomad": True,
            "use_online_vep": True,
            "use_online_pubmed": True,
            "use_online_litvar": True,
            "provider_cache_dir": str(tmp_path / "providers"),
        }
    )

    pipeline_options = runtime_options_to_pipeline_dict(runtime)
    sources = pipeline_options["data_sources"]["sources"]

    assert sources["clinvar"] == {
        "mode": "online",
        "online_enabled": True,
        "source_version": "NCBI ClinVar E-utilities live",
        "cache_dir": f"{tmp_path}/providers/clinvar",
    }
    assert sources["population"] == {
        "mode": "online",
        "online_enabled": True,
        "source_version": "gnomAD gnomad_r4 live GraphQL",
        "cache_dir": f"{tmp_path}/providers/gnomad",
    }
    assert sources["computational"] == {
        "mode": "online",
        "online_enabled": True,
        "source_version": "Ensembl REST VEP live",
        "cache_dir": f"{tmp_path}/providers/vep",
    }
    assert sources["literature"] == {
        "mode": "online",
        "online_enabled": True,
        "source_version": "PubMed/LitVar live",
        "cache_dir": f"{tmp_path}/providers/literature",
    }


def test_existing_data_sources_overrides_are_preserved(tmp_path) -> None:
    runtime = normalize_runtime_options(
        {
            "use_online_clinvar": True,
            "provider_cache_dir": str(tmp_path / "providers"),
            "data_sources": {
                "sources": {
                    "clinvar": {
                        "source_version": "custom-clinvar",
                        "cache_dir": str(tmp_path / "custom-clinvar"),
                    },
                    "population": {"mode": "local_file", "local_file": "/tmp/gnomad.jsonl"},
                }
            },
        }
    )

    sources = runtime_options_to_pipeline_dict(runtime)["data_sources"]["sources"]

    assert sources["clinvar"]["mode"] == "online"
    assert sources["clinvar"]["online_enabled"] is True
    assert sources["clinvar"]["source_version"] == "custom-clinvar"
    assert sources["clinvar"]["cache_dir"] == str(tmp_path / "custom-clinvar")
    assert sources["population"] == {"mode": "local_file", "local_file": "/tmp/gnomad.jsonl"}


def test_report_context_provider_runtime_fields_are_preserved() -> None:
    runtime = normalize_runtime_options(
        {
            "provider_cache_dir": "/tmp/providers",
            "provider_timeout": 12.5,
            "provider_email": "curator@example.org",
            "provider_user_agent": "vpr-test",
            "report_language": "zh",
            "report_mode": "clinician",
            "confirmed_context": {"disease": "Hypophosphatasia"},
            "disease": "Hypophosphatasia",
            "inheritance": "autosomal_dominant",
        }
    )

    assert runtime.provider_cache_dir == "/tmp/providers"
    assert runtime.provider_timeout == 12.5
    assert runtime.provider_email == "curator@example.org"
    assert runtime.provider_user_agent == "vpr-test"
    assert runtime.report_language == "zh"
    assert runtime.report_mode == "clinician"
    assert runtime.disease == "Hypophosphatasia"
    assert runtime.inheritance == "autosomal_dominant"
    assert runtime.confirmed_context == {"disease": "Hypophosphatasia"}


def test_top_level_reviewed_evidence_precedence_is_preserved() -> None:
    runtime = normalize_runtime_options(
        options={"reviewed_evidence": [{"id": "option-review"}]},
        top_level={"reviewed_evidence": [{"id": "top-review"}]},
    )

    assert runtime.reviewed_evidence == [{"id": "top-review"}]
    assert runtime.option_sources["reviewed_evidence"] == "top_level"
    assert any("top-level reviewed_evidence was used" in item for item in runtime.normalization_warnings)


def test_supplemental_evidence_mock_alias_is_preserved() -> None:
    runtime = normalize_runtime_options(
        {
            "supplemental_evidence_items": [{"id": "supplemental"}],
            "mock_supplemental_evidence_items": [{"id": "mock-supplemental"}],
        }
    )
    pipeline_options = runtime_options_to_pipeline_dict(runtime)

    assert runtime.supplemental_evidence_items == [{"id": "mock-supplemental"}]
    assert pipeline_options["supplemental_evidence_items"] == [{"id": "mock-supplemental"}]
    assert pipeline_options["mock_supplemental_evidence_items"] == [{"id": "mock-supplemental"}]


def test_passthrough_preserves_legacy_option_surface() -> None:
    legacy_options = {
        "vcep_profile_file": "/tmp/profile.yaml",
        "population_thresholds": {"ba1_af_threshold": 0.05},
        "computational_thresholds": {"revel_pathogenic": 0.75},
        "clinvar_records": [{"variation_id": "123"}],
        "population_frequency": {"overall_af": 0.01},
        "literature_records": [{"pmid": "1"}],
        "transcript_fixture": "/tmp/transcripts.jsonl",
        "include_clinvar": False,
        "include_population": False,
        "include_computational": False,
        "include_literature": False,
        "data_sources": {"sources": {"clinvar": {"mode": "mock"}}},
    }

    runtime = normalize_runtime_options(legacy_options)
    pipeline_options = runtime_options_to_pipeline_dict(runtime)

    for key, value in legacy_options.items():
        assert runtime.passthrough_options[key] == value
        assert pipeline_options[key] == value


def test_runtime_options_to_pipeline_dict_is_legacy_compatible(tmp_path) -> None:
    runtime = RuntimeOptions(
        use_online_clinvar=True,
        provider_cache_dir=str(tmp_path),
        report_language="en",
        passthrough_options={"include_literature": False},
    )

    pipeline_options = runtime_options_to_pipeline_dict(apply_online_provider_modes(runtime))

    assert pipeline_options["mock_mode"] is True
    assert pipeline_options["use_online_clinvar"] is True
    assert pipeline_options["provider_cache_dir"] == str(tmp_path)
    assert pipeline_options["report_language"] == "en"
    assert pipeline_options["include_literature"] is False
    assert pipeline_options["data_sources"]["sources"]["clinvar"]["mode"] == "online"


def test_rate_variant_final_classification_unchanged_for_default_call() -> None:
    baseline = rate_variant(_variant_payload())
    with_explicit_default_options = rate_variant(_variant_payload({"mock_mode": True}))

    assert baseline["final_classification"] == with_explicit_default_options["final_classification"]
    assert _stable_evidence_summary(baseline["applied_evidence"]) == _stable_evidence_summary(
        with_explicit_default_options["applied_evidence"]
    )
    assert _stable_evidence_summary(baseline["candidate_evidence"]) == _stable_evidence_summary(
        with_explicit_default_options["candidate_evidence"]
    )
    assert with_explicit_default_options["mock_mode"] is True


def test_rate_variant_online_options_still_configure_data_source_modes(tmp_path) -> None:
    result = rate_variant(
        _variant_payload(
            {
                "use_online_clinvar": True,
                "provider_cache_dir": str(tmp_path / "providers"),
                "include_clinvar": False,
                "include_population": False,
                "include_computational": False,
                "include_literature": False,
            }
        )
    )

    assert result["status"] == "ok"
    assert result["mock_mode"] is True
    assert result["offline_default_mode"] is True
    assert result["data_source_modes"]["clinvar"] == "online"
    assert result["provider_mode_summary"]["clinvar"]["requested_mode"] == "online"
    assert result["provider_mode_summary"]["clinvar"]["configured_mode"] == "online"
