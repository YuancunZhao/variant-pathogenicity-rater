from __future__ import annotations

import json
from pathlib import Path

from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pipeline.real_world import run_annotation_batch_workflow


ROOT = Path(__file__).resolve().parents[1]
TOY_DIR = ROOT / "knowledge_base" / "rule_overrides" / "toy"


def _toy_file(name: str) -> str:
    return str(TOY_DIR / name)


def _population_payload(*, toy_file: str | None = None, options: dict[str, object] | None = None) -> dict[str, object]:
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
            "data_source": "toy_population_fixture",
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
    if toy_file:
        base_options.update(
            {
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_file": toy_file,
            }
        )
    if options:
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


def _pvs1_payload(*, toy_file: str | None = None) -> dict[str, object]:
    options: dict[str, object] = {
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
    if toy_file:
        options.update(
            {
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_file": toy_file,
            }
        )
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
        "options": options,
    }


def test_toy_profiles_are_not_loaded_by_default_kb_scan() -> None:
    result = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_kb_dir": str(ROOT / "knowledge_base"),
            }
        )
    )

    assert result["vcep_signal"]["profiles_checked"] == 0
    assert result["vcep_signal"]["matches"] == []
    assert result["vcep_override_context"]["applied"] is False
    assert [item["code"] for item in result["applied_evidence"]] == ["BS1"]


def test_toy_population_threshold_override_applies_with_explicit_path_and_keeps_quality_gates() -> None:
    toy_file = _toy_file("brca1_population_override.approved.json")
    generic = rate_variant(_population_payload())
    overridden = rate_variant(_population_payload(toy_file=toy_file))
    low_quality = rate_variant(
        _population_payload(
            toy_file=toy_file,
            options={
                "population_frequency": {
                    "variant_id": "GRCh38-1-100-A-G",
                    "overall_af": 0.03,
                    "max_pop_af": 0.03,
                    "population_name": "global",
                    "allele_count": 1,
                    "allele_number": 100,
                    "homozygote_count": 0,
                    "data_source": "toy_population_fixture",
                    "is_absent": False,
                    "coverage_quality": "high",
                    "population_match": True,
                }
            },
        )
    )

    assert [item["code"] for item in generic["applied_evidence"]] == ["BS1"]
    assert [item["code"] for item in overridden["applied_evidence"]] == ["BA1"]
    assert overridden["applied_evidence"][0]["supporting_data"]["population_evidence_decision"][
        "thresholds_used"
    ]["ba1_af_threshold"] == 0.02
    assert low_quality["applied_evidence"] == []
    candidate = next(item for item in low_quality["review_note_evidence"] if item["code"] == "BA1")
    assert candidate["candidate_only"] is True
    assert any("allele" in reason.lower() for reason in candidate["supporting_data"]["blocking_reasons"])


def test_toy_pvs1_disable_moves_applied_pvs1_to_review_note() -> None:
    generic = rate_variant(_pvs1_payload())
    disabled = rate_variant(_pvs1_payload(toy_file=_toy_file("brca1_pvs1_disabled.approved.json")))

    assert any(item["code"] == "PVS1" for item in generic["applied_evidence"])
    assert not any(item["code"] == "PVS1" for item in disabled["applied_evidence"])
    pvs1 = next(item for item in disabled["review_note_evidence"] if item["code"] == "PVS1")
    assert pvs1["candidate_only"] is True
    assert pvs1["supporting_data"]["vcep_override"]["override_applied_to_item"] is False
    assert any("PVS1 disabled" in reason for reason in pvs1["supporting_data"]["blocking_reasons"])
    assert disabled["classification_result"]["applied_combination_rule"] == "default_vus"


def test_toy_computational_stricter_threshold_note_does_not_create_applied_evidence() -> None:
    example = json.loads((ROOT / "examples" / "computational_pp3_input.json").read_text())
    result = rate_variant(
        {
            "gene": "BRAF",
            "chromosome": "7",
            "position": 140753336,
            "ref": "A",
            "alt": "T",
            "disease": "Example disease",
            "inheritance": "autosomal dominant",
            "options": {
                "include_population": False,
                "include_clinvar": False,
                "include_literature": False,
                "computational_predictions": example["computational_predictions"],
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_file": _toy_file("braf_computational_strict.approved.json"),
            },
        }
    )

    assert result["applied_evidence"] == []
    candidate = next(item for item in result["review_note_evidence"] if item["code"] == "PP3")
    assert candidate["candidate_only"] is True
    assert candidate["supporting_data"]["vcep_override"]["profile"]["profile_id"] == (
        "toy-demo-braf-computational-strict-v1"
    )
    assert any(
        flag["code"] == "TOY_PROFILE_TESTING_DEMO_ONLY"
        for flag in result["classification_result"]["review_flags"]
    )


def test_toy_ps1_pm5_candidate_only_override_blocks_applied() -> None:
    result = rate_variant(
        {
            "gene": "GENE1",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "hgvs_p": "NP_000001.1:p.Lys26Arg",
            "chromosome": "1",
            "position": 123,
            "ref": "A",
            "alt": "G",
            "disease": "Example disease",
            "inheritance": "autosomal dominant",
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_literature": False,
                "clinvar_records": [
                    {
                        "variation_id": "cv-ps1",
                        "gene": "GENE1",
                        "transcript": "NM_000001.1",
                        "hgvs_c": "NM_000001.1:c.77A>G",
                        "hgvs_p": "NP_000001.1:p.Lys26Arg",
                        "clinical_significance": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "conditions": ["Example disease"],
                        "submitter_count": 3,
                        "conflicting_interpretations": False,
                        "germline_or_somatic": "germline",
                    }
                ],
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_file": _toy_file("gene1_ps1_pm5_candidate.approved.json"),
            },
        }
    )

    assert result["applied_evidence"] == []
    candidate = next(item for item in result["review_note_evidence"] if item["code"] == "PS1")
    assert candidate["candidate_only"] is True
    assert candidate["supporting_data"]["vcep_override"]["profile"]["profile_id"] == (
        "toy-demo-gene1-ps1-pm5-candidate-v1"
    )


def test_toy_disabled_criterion_is_visible_as_review_note_not_silently_deleted() -> None:
    result = rate_variant(
        _population_payload(toy_file=_toy_file("brca1_bs1_disabled.approved.json"))
    )

    assert result["applied_evidence"] == []
    candidate = next(item for item in result["review_note_evidence"] if item["code"] == "BS1")
    assert candidate["applied"] is False
    assert candidate["candidate_only"] is True
    assert candidate["supporting_data"]["vcep_override"]["override_applied_to_item"] is False
    assert any("BS1 disabled" in note for note in candidate["supporting_data"]["vcep_override"]["notes"])
    assert any(
        flag["code"] == "VCEP_CRITERION_DISABLED_OR_CANDIDATE_ONLY"
        for flag in candidate["review_flags"]
    )


def test_toy_draft_and_provisional_profiles_are_signal_only() -> None:
    for filename, expected_status in [
        ("brca1_population_signal.draft.json", "draft"),
        ("brca1_population_signal.provisional.json", "provisional"),
    ]:
        result = rate_variant(_population_payload(toy_file=_toy_file(filename)))

        assert result["vcep_signal"]["matches"][0]["profile"]["status"] == expected_status
        assert result["vcep_override_context"]["applied"] is False
        assert [item["code"] for item in result["applied_evidence"]] == ["BS1"]
        assert any(expected_status in item.lower() for item in result["limitations"])


def test_toy_deprecated_profile_is_limitation_only() -> None:
    result = rate_variant(_pvs1_payload(toy_file=_toy_file("brca1_pvs1_deprecated.deprecated.json")))

    assert result["vcep_signal"]["matches"][0]["profile"]["status"] == "deprecated"
    assert result["vcep_override_context"]["applied"] is False
    assert any("Deprecated VCEP profile" in item for item in result["limitations"])
    assert any(item["code"] == "PVS1" for item in result["applied_evidence"])


def test_toy_conflicting_approved_profiles_block_override() -> None:
    result = rate_variant(
        _population_payload(toy_file=_toy_file("brca1_conflicting_approved.json"))
    )

    assert result["vcep_override_context"]["applied"] is False
    assert len(result["vcep_signal"]["matches"]) == 2
    assert any(flag["code"] == "VCEP_PROFILE_CONFLICT" for flag in result["review_flags"])
    assert [item["code"] for item in result["applied_evidence"]] == ["BS1"]


def test_report_and_provenance_show_toy_profile_origin() -> None:
    result = rate_variant(
        _population_payload(toy_file=_toy_file("brca1_population_override.approved.json"))
    )

    summary = result["report"]["summary"]["vcep_profile_context"]
    active = summary["override_context"]["active_profile"]
    assert active["profile_id"] == "toy-demo-brca1-population-override-v1"
    assert "TOY PROFILE - TESTING/DEMO ONLY" in active["source"]
    assert result["provenance"]["vcep_override"]["active_profile"]["profile_id"] == active["profile_id"]
    assert "toy-demo-brca1-population-override-v1" in result["report_text"]


def test_toy_batch_and_annotated_batch_preserve_vcep_profile_summary() -> None:
    toy_file = _toy_file("brca1_population_override.approved.json")
    batch = rate_variant_batch({"records": [_population_payload(toy_file=toy_file)]})
    batch_summary = batch["results"][0]["vcep_profile_summary"]

    annotated = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": [
                {
                    "gene": "BRCA1",
                    "transcript": "NM_007294.4",
                    "hgvs_c": "NM_007294.4:c.68A>G",
                    "hgvs_p": "NP_009225.1:p.Glu23Val",
                    "consequence": "missense_variant",
                    "chrom": "1",
                    "pos": 100,
                    "ref": "A",
                    "alt": "G",
                }
            ],
            "gene_disease_context": {
                "gene": "BRCA1",
                "disease": "Hereditary breast and ovarian cancer syndrome",
                "inheritance": "autosomal dominant",
                "disease_prevalence": 0.0001,
                "population_ancestry": "global",
            },
            "options": {
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
                    "data_source": "toy_population_fixture",
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
                "include_vcep_signals": True,
                "apply_vcep_overrides": True,
                "vcep_profile_file": toy_file,
            },
        }
    )
    annotated_summary = annotated["results"][0]["vcep_profile_summary"]

    assert batch_summary["override_context"]["override_applied"] is True
    assert batch_summary["override_context"]["active_profile"]["profile_id"] == (
        "toy-demo-brca1-population-override-v1"
    )
    assert annotated_summary["override_context"]["override_applied"] is True
    assert annotated_summary["override_context"]["active_profile"]["profile_id"] == (
        "toy-demo-brca1-population-override-v1"
    )


def test_toy_signal_only_keeps_classification_combiner_behavior_unchanged() -> None:
    generic = rate_variant(_population_payload())
    signal_only = rate_variant(
        _population_payload(
            options={
                "include_vcep_signals": True,
                "vcep_profile_file": _toy_file("brca1_population_override.approved.json"),
            }
        )
    )

    assert signal_only["final_classification"] == generic["final_classification"]
    assert signal_only["classification_result"]["applied_combination_rule"] == generic[
        "classification_result"
    ]["applied_combination_rule"]
    assert [item["code"] for item in signal_only["applied_evidence"]] == [
        item["code"] for item in generic["applied_evidence"]
    ]
