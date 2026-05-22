from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "real_data_smoke_cases.json"
CLINVAR_FIXTURE_PATH = ROOT / "data" / "fixtures" / "clinvar_smoke.jsonl"
POPULATION_FIXTURE_PATH = ROOT / "data" / "fixtures" / "population_smoke.jsonl"

VALID_CLASSIFICATIONS = {
    "pathogenic",
    "likely_pathogenic",
    "vus",
    "likely_benign",
    "benign",
}


def _jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        fixture_id = record.get("fixture_id")
        assert fixture_id, f"{path}:{line_number} is missing fixture_id"
        records[fixture_id] = record
    return records


def _cases() -> list[dict[str, Any]]:
    payload = json.loads(CASE_PATH.read_text())
    return payload["cases"]


CLINVAR_FIXTURES = _jsonl_by_id(CLINVAR_FIXTURE_PATH)
POPULATION_FIXTURES = _jsonl_by_id(POPULATION_FIXTURE_PATH)


def _population_payload(case: dict[str, Any]) -> dict[str, Any] | None:
    fixture_id = case.get("population_fixture_id")
    if fixture_id is None:
        return None
    fixture = dict(POPULATION_FIXTURES[fixture_id])
    fixture.pop("fixture_id")
    return fixture


def _clinvar_records(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [CLINVAR_FIXTURES[fixture_id] for fixture_id in case["clinvar_fixture_ids"]]


def _pipeline_payload(case: dict[str, Any]) -> dict[str, Any]:
    variant = case["variant"]
    options: dict[str, Any] = {
        "mock_mode": True,
        "population_thresholds": {
            "disease_specific": True,
            "penetrance_provided": True,
            "ba1_af_threshold": 0.05,
            "bs1_af_threshold": 0.01,
            "pm2_af_threshold": 0.0001,
            "min_allele_number": 2000,
        },
        "computational_predictions": case["computational_predictions"],
        "clinvar_records": _clinvar_records(case),
        "include_literature": False,
        "literature_records": [],
        "mock_supplemental_evidence_items": [],
    }
    population_payload = _population_payload(case)
    if population_payload is not None:
        options["population_frequency"] = population_payload

    return {
        "gene": variant["gene"],
        "transcript": variant["transcript"],
        "hgvs_c": variant["hgvs_c"],
        "hgvs_p": variant["hgvs_p"],
        "chromosome": variant["chromosome"],
        "position": variant["position"],
        "ref": variant["ref"],
        "alt": variant["alt"],
        "genome_build": variant.get("genome_build", "GRCh38"),
        "disease": case["disease_context"]["disease"],
        "inheritance": case["disease_context"]["inheritance"],
        "gene_disease_context": case["disease_context"],
        "options": options,
    }


def _is_candidate(item: dict[str, Any]) -> bool:
    supporting_data = item.get("supporting_data") or {}
    return (
        item["strength"] == "none"
        or supporting_data.get("candidate_only") is True
        or supporting_data.get("evidence_status") == "candidate"
        or supporting_data.get("applied") is False
    )


def _codes(items: list[dict[str, Any]]) -> list[str]:
    return sorted(item["code"] for item in items)


def _review_flag_codes(result: dict[str, Any]) -> set[str]:
    codes = {flag["code"] for flag in result["classification_result"]["review_flags"]}
    for item in result["evidence_items"]:
        codes.update(flag["code"] for flag in item.get("review_flags", []))
    for step in result["step_results"].values():
        if isinstance(step, dict):
            codes.update(flag["code"] for flag in step.get("review_flags", []))
    return codes


def _section(report_text: str, heading: str, next_heading: str | None = None) -> str:
    start = report_text.index(heading)
    if next_heading is None:
        return report_text[start:]
    end = report_text.index(next_heading, start)
    return report_text[start:end]


def test_real_data_smoke_case_set_shape_and_scenario_coverage() -> None:
    cases = _cases()
    scenario_counts = Counter(case["scenario"] for case in cases)

    assert len(cases) >= 10
    assert scenario_counts["high_confidence_p_lp_lof"] >= 2
    assert scenario_counts["high_af_benign"] >= 2
    assert scenario_counts["clinvar_conflict"] >= 2
    assert scenario_counts["vus"] >= 2
    assert scenario_counts["pm2_pp3_still_vus"] >= 1
    assert scenario_counts["pvs1_edge_no_overcall"] >= 1

    required_fields = {
        "case_id",
        "scenario",
        "variant",
        "disease_context",
        "expected_behavior",
        "expected_applied_evidence",
        "expected_candidate_evidence",
        "allowed_classifications",
        "expected_review_flags",
        "explanation",
    }
    for case in cases:
        assert required_fields.issubset(case), case["case_id"]
        assert set(case["allowed_classifications"]).issubset(VALID_CLASSIFICATIONS)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_real_data_smoke_case_runs_full_rate_variant_pipeline(case: dict[str, Any]) -> None:
    result = rate_variant(_pipeline_payload(case))

    assert result["status"] == "ok"
    assert result["mock_mode"] is True
    assert result["final_classification"] in case["allowed_classifications"]
    assert result["classification_result"]["final_classification"] == result["final_classification"]
    assert result["human_review_required"] is True
    assert result["classification_result"]["human_review_required"] is True

    completed_steps = {
        event["tool_name"]
        for event in result["audit_trail"]
        if event["event_type"].endswith("_completed")
    }
    assert {
        "normalize_variant",
        "query_population_frequency",
        "evaluate_population_rules",
        "evaluate_computational_evidence",
        "evaluate_pvs1",
        "query_clinvar",
        "load_mock_supplemental_evidence",
        "classify_acmg",
        "generate_report",
    }.issubset(completed_steps)

    applied_items = [item for item in result["evidence_items"] if not _is_candidate(item)]
    candidate_items = [item for item in result["evidence_items"] if _is_candidate(item)]
    assert _codes(applied_items) == sorted(case["expected_applied_evidence"])
    assert _codes(candidate_items) == sorted(case["expected_candidate_evidence"])

    review_codes = _review_flag_codes(result)
    assert set(case["expected_review_flags"]).issubset(review_codes)

    for item in result["evidence_items"]:
        if item["source"]["name"] == "ClinVar":
            assert _is_candidate(item)
            assert item["strength"] == "none"
            assert item["supporting_data"]["candidate_only"] is True
            assert item["supporting_data"]["automatic_application"] is False

    report_text = result["report_text"]
    assert "## Triggered ACMG Evidence" in report_text
    assert "## Candidate / Review-Note Evidence" in report_text
    applied_section = _section(
        report_text,
        "## Triggered ACMG Evidence",
        "## Candidate / Review-Note Evidence",
    )
    candidate_section = _section(
        report_text,
        "## Candidate / Review-Note Evidence",
        "## Conflicting Evidence",
    )
    assert "source: ClinVar" not in applied_section
    for code in case["expected_applied_evidence"]:
        assert f": {code} /" in applied_section
    for code in case["expected_candidate_evidence"]:
        assert f": {code} /" in candidate_section


def test_real_data_smoke_no_population_record_does_not_trigger_pm2() -> None:
    case = next(case for case in _cases() if case["case_id"] == "smoke-atm-start-loss-edge")
    result = rate_variant(_pipeline_payload(case))

    all_codes = [item["code"] for item in result["evidence_items"]]
    assert "PM2" not in all_codes
    population_result = result["step_results"]["query_population_frequency"]
    assert population_result["overall_af"] is None
    assert population_result["max_pop_af"] is None
    assert population_result["is_absent"] is False
    assert "evaluate_population_rules" not in result["step_results"] or all(
        item["code"] != "PM2" for item in result["step_results"]["evaluate_population_rules"]
    )


def test_real_data_smoke_conflicting_applied_evidence_defaults_to_vus_review() -> None:
    case = next(case for case in _cases() if case["case_id"] == "smoke-brca1-lof-plp")
    payload = _pipeline_payload(case)
    payload["options"]["population_frequency"] = {
        **payload["options"]["population_frequency"],
        "overall_af": 0.08,
        "max_pop_af": 0.08,
        "is_absent": False,
        "allele_count": 8000,
        "allele_number": 100000,
    }

    result = rate_variant(payload)

    assert result["final_classification"] == "vus"
    assert "OPPOSING_PATHOGENIC_AND_BENIGN_EVIDENCE" in _review_flag_codes(result)
    applied_codes = _codes([item for item in result["evidence_items"] if not _is_candidate(item)])
    assert "PVS1" in applied_codes
    assert "BA1" in applied_codes
