from __future__ import annotations

from copy import deepcopy

from server import build_registry

from variant_pathogenicity_rater.cli import build_parser
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


def _profile(**overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "profile_id": "brca1-hboc-v1",
        "gene": "BRCA1",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal dominant",
        "vcep_name": "BRCA1 VCEP",
        "source": "local-test-vcep-profile",
        "version": "2026-05-27",
        "status": "approved",
        "effective_date": "2026-05-27",
        "citations": ["PMID:000000"],
        "notes": ["Unit-test profile."],
        "applicable_transcripts": ["NM_007294.4"],
        "rule_signals": [{"criterion": "PVS1", "message": "Gene-specific PVS1 guidance exists."}],
        "population_threshold_overrides": {},
        "pvs1_overrides": {},
        "computational_overrides": {},
        "ps1_pm5_overrides": {},
        "disabled_criteria": [],
        "review_required_flags": [
            {
                "code": "VCEP_TEST_REVIEW_REQUIRED",
                "message": "Test VCEP profile requires review.",
            }
        ],
        "provenance": {"fixture": "test_vcep_signal_override_framework"},
    }
    profile.update(overrides)
    return profile


def _base_payload(*, options: dict[str, object] | None = None) -> dict[str, object]:
    base_options: dict[str, object] = {
        "include_population": False,
        "include_computational": False,
        "include_clinvar": False,
        "include_literature": False,
        "annotation_records": [
            {
                "gene": "BRCA1",
                "transcript": "NM_007294.4",
                "hgvs_c": "NM_007294.4:c.68_69delAG",
                "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
                "consequence": "frameshift_variant",
                "exon": "2/24",
                "canonical": True,
                "mane_select": True,
                "transcript_biotype": "protein_coding",
            }
        ],
    }
    if options:
        base_options.update(options)
    return {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43124027,
        "ref": "CA",
        "alt": "C",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal dominant",
        "gene_disease_context": {
            "gene": "BRCA1",
            "disease": "Hereditary breast and ovarian cancer syndrome",
            "inheritance": "autosomal dominant",
            "lof_is_known_mechanism": True,
            "transcript_is_biologically_relevant": True,
            "nmd_prediction_available": True,
            "nmd_predicted": True,
            "last_exon_information": {
                "is_in_last_exon": False,
                "exon_number": 2,
                "total_exons": 24,
            },
        },
        "options": base_options,
    }


def _population_payload(*, options: dict[str, object]) -> dict[str, object]:
    base_options: dict[str, object] = {
        "include_population": True,
        "include_computational": False,
        "include_clinvar": False,
        "include_literature": False,
        "population_frequency": {
            "variant_id": "GRCh38-1-100-A-G",
            "overall_af": 0.03,
            "max_pop_af": 0.03,
            "population_name": "global",
            "allele_count": 30,
            "allele_number": 100000,
            "homozygote_count": 0,
            "data_source": "test_population",
            "is_absent": False,
            "coverage_quality": "high",
            "population_match": True,
        },
        "population_thresholds": {
            "disease_specific": True,
            "penetrance_provided": True,
            "ba1_af_threshold": 0.05,
            "bs1_af_threshold": 0.01,
        },
    }
    base_options.update(options)
    return {
        "gene": "BRCA1",
        "chromosome": "1",
        "position": 100,
        "ref": "A",
        "alt": "G",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal dominant",
        "gene_disease_context": {
            "gene": "BRCA1",
            "disease": "Hereditary breast and ovarian cancer syndrome",
            "inheritance": "autosomal dominant",
            "disease_prevalence": 0.0001,
            "population_ancestry": "global",
        },
        "options": base_options,
    }


def test_gene_level_signal_only_no_classification_change() -> None:
    without_signal = rate_variant(_base_payload())
    with_signal = rate_variant(
        _base_payload(
            options={
                "include_vcep_signals": True,
                "vcep_profile_records": [_profile()],
            }
        )
    )

    assert with_signal["final_classification"] == without_signal["final_classification"]
    assert [item["code"] for item in with_signal["applied_evidence"]] == [
        item["code"] for item in without_signal["applied_evidence"]
    ]
    assert with_signal["classification_result"]["applied_combination_rule"] == without_signal[
        "classification_result"
    ]["applied_combination_rule"]
    assert with_signal["vcep_signal"]["matches"][0]["profile"]["profile_id"] == "brca1-hboc-v1"
    assert any(flag["code"] == "VCEP_PROFILE_MATCH" for flag in with_signal["review_flags"])


def test_profile_missing_falls_back_to_generic_behavior() -> None:
    result = rate_variant(
        _base_payload(
            options={
                "include_vcep_signals": True,
                "vcep_profile_records": [_profile(gene="OTHER")],
            }
        )
    )

    assert result["vcep_signal"]["matches"] == []
    assert result["vcep_override_context"]["applied"] is False
    assert not result["provenance"]["vcep_override"]["override_applied"]


def test_approved_population_threshold_override_is_reported() -> None:
    generic = rate_variant(_population_payload(options={}))
    overridden = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [
                    _profile(
                        applicable_transcripts=[],
                        population_threshold_overrides={"ba1_af_threshold": 0.02},
                    )
                ],
            }
        )
    )

    assert [item["code"] for item in generic["applied_evidence"]] == ["BS1"]
    assert [item["code"] for item in overridden["applied_evidence"]] == ["BA1"]
    item = overridden["applied_evidence"][0]
    assert item["supporting_data"]["population_evidence_decision"]["thresholds_used"]["ba1_af_threshold"] == 0.02
    assert item["supporting_data"]["vcep_override"]["profile"]["profile_id"] == "brca1-hboc-v1"
    assert "## VCEP Signal / Rule Profile" in overridden["report_text"]


def test_draft_profile_is_signal_only() -> None:
    result = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [
                    _profile(
                        status="draft",
                        applicable_transcripts=[],
                        population_threshold_overrides={"ba1_af_threshold": 0.02},
                    )
                ],
            }
        )
    )

    assert result["vcep_override_context"]["applied"] is False
    assert [item["code"] for item in result["applied_evidence"]] == ["BS1"]
    assert any("draft" in item.lower() for item in result["limitations"])


def test_deprecated_profile_is_limitation_only() -> None:
    result = rate_variant(
        _base_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [_profile(status="deprecated", pvs1_overrides={"disable": True})],
            }
        )
    )

    assert result["vcep_override_context"]["applied"] is False
    assert any("Deprecated VCEP profile" in item for item in result["limitations"])


def test_pvs1_disabled_by_profile_stays_out_of_combiner() -> None:
    generic = rate_variant(_base_payload())
    disabled = rate_variant(
        _base_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [_profile(pvs1_overrides={"disable": True})],
            }
        )
    )

    assert any(item["code"] == "PVS1" for item in generic["applied_evidence"])
    assert not any(item["code"] == "PVS1" for item in disabled["applied_evidence"])
    pvs1 = next(item for item in disabled["review_note_evidence"] if item["code"] == "PVS1")
    assert pvs1["candidate_only"] is True
    assert pvs1["supporting_data"]["vcep_override"]["override_applied_to_item"] is False
    assert disabled["classification_result"]["applied_combination_rule"] == "default_vus"


def test_profile_conflict_blocks_overrides() -> None:
    second = deepcopy(
        _profile(
            profile_id="brca1-hboc-v2",
            version="2026-05-28",
            applicable_transcripts=[],
        )
    )
    result = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [
                    _profile(applicable_transcripts=[], population_threshold_overrides={"ba1_af_threshold": 0.02}),
                    second,
                ],
            }
        )
    )

    assert result["vcep_override_context"]["applied"] is False
    assert any(flag["code"] == "VCEP_PROFILE_CONFLICT" for flag in result["review_flags"])
    assert [item["code"] for item in result["applied_evidence"]] == ["BS1"]


def test_report_and_provenance_show_active_profile() -> None:
    result = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [
                    _profile(
                        applicable_transcripts=[],
                        population_threshold_overrides={"ba1_af_threshold": 0.02},
                    )
                ],
            }
        )
    )

    assert result["report"]["summary"]["vcep_profile_context"]["override_context"]["override_applied"] is True
    assert result["provenance"]["vcep_override"]["active_profile"]["profile_id"] == "brca1-hboc-v1"
    assert "brca1-hboc-v1" in result["report_text"]


def test_disabled_criterion_does_not_make_candidate_applied() -> None:
    result = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_records": [_profile(applicable_transcripts=[], disabled_criteria=["BS1"])],
            }
        )
    )

    assert result["applied_evidence"] == []
    candidate = next(item for item in result["review_note_evidence"] if item["code"] == "BS1")
    assert candidate["strength"] == "none"
    assert candidate["applied"] is False
    assert candidate["candidate_only"] is True


def test_cli_and_mcp_accept_vcep_options() -> None:
    args = build_parser().parse_args(
        [
            "rate",
            "--gene",
            "BRCA1",
            "--chromosome",
            "1",
            "--position",
            "100",
            "--ref",
            "A",
            "--alt",
            "G",
            "--include-vcep-signals",
            "--apply-vcep-overrides",
            "--vcep-profile-file",
            "profiles.json",
        ]
    )
    assert args.include_vcep_signals is True
    assert args.apply_vcep_overrides is True
    assert args.vcep_profile_file == "profiles.json"

    rate_tool = next(tool for tool in build_registry().list_tools() if tool.name == "rate_variant")
    options = rate_tool.input_schema["properties"]["options"]["properties"]
    assert "include_vcep_signals" in options
    assert "apply_vcep_overrides" in options
    assert "vcep_profile_records" in options
