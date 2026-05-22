from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


BENCHMARK_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmark_snv_cases.json"
VALID_CLASSIFICATIONS = {
    "pathogenic",
    "likely_pathogenic",
    "vus",
    "likely_benign",
    "benign",
}


def _benchmark_cases() -> list[dict[str, Any]]:
    payload = json.loads(BENCHMARK_PATH.read_text())
    return payload["cases"]


def _variant_id(case: dict[str, Any]) -> str:
    genomic = case["genomic"]
    return (
        f"{genomic.get('genome_build', 'GRCh38')}-"
        f"{genomic['chromosome']}-{genomic['position']}-"
        f"{genomic['ref']}-{genomic['alt']}"
    )


def _pipeline_payload(case: dict[str, Any]) -> dict[str, Any]:
    genomic = case["genomic"]
    population = dict(case["mock_population_data"])
    population["variant_id"] = _variant_id(case)

    return {
        "gene": case["gene"],
        "transcript": case["transcript"],
        "hgvs_c": case["hgvs_c"],
        "hgvs_p": case["hgvs_p"],
        "chromosome": genomic["chromosome"],
        "position": genomic["position"],
        "ref": genomic["ref"],
        "alt": genomic["alt"],
        "genome_build": genomic.get("genome_build", "GRCh38"),
        "disease": case["disease"],
        "inheritance": case["inheritance"],
        "gene_disease_context": case["gene_disease_context"],
        "options": {
            "mock_mode": True,
            "population_frequency": population,
            "population_thresholds": case["population_thresholds"],
            "computational_predictions": case["mock_computational_prediction"],
            "clinvar_records": [case["mock_clinvar_record"]],
            "literature_records": case["mock_literature_evidence"],
            "mock_supplemental_evidence_items": case["mock_applied_evidence"],
        },
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


def test_benchmark_dataset_shape_and_classification_coverage() -> None:
    cases = _benchmark_cases()

    assert len(cases) >= 20
    counts = Counter(case["expected_classification"] for case in cases)
    assert set(counts).issubset(VALID_CLASSIFICATIONS)
    assert counts["pathogenic"] >= 4
    assert counts["likely_pathogenic"] >= 4
    assert counts["vus"] >= 4
    assert counts["likely_benign"] >= 4
    assert counts["benign"] >= 4

    required_fields = {
        "gene",
        "transcript",
        "hgvs_c",
        "hgvs_p",
        "variant_type",
        "disease",
        "inheritance",
        "mock_population_data",
        "mock_computational_prediction",
        "mock_clinvar_record",
        "mock_literature_evidence",
        "expected_classification",
        "expected_applied_evidence",
        "expected_candidate_evidence",
        "expected_review_flags",
        "rationale",
    }
    for case in cases:
        assert required_fields.issubset(case), case["case_id"]


@pytest.mark.parametrize("case", _benchmark_cases(), ids=lambda case: case["case_id"])
def test_benchmark_case_runs_full_rate_variant_pipeline(case: dict[str, Any]) -> None:
    result = rate_variant(_pipeline_payload(case))

    assert result["status"] == "ok"
    assert result["mock_mode"] is True
    assert result["final_classification"] == case["expected_classification"]
    assert result["classification_result"]["final_classification"] == case["expected_classification"]
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
        "search_literature_evidence",
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
    for code in case["expected_applied_evidence"]:
        assert f": {code} /" in applied_section
    for code in case["expected_candidate_evidence"]:
        assert f": {code} /" in candidate_section


def test_benchmark_safety_scenarios_are_present() -> None:
    cases = _benchmark_cases()
    rationales = " ".join(case["rationale"] for case in cases).lower()

    expected_phrases = [
        "pvs1 very strong plus pm2_supporting",
        "pm2 alone remains vus",
        "pp3 alone remains vus",
        "pm2 plus pp3 remains vus",
        "ba1-level frequency is candidate-only",
        "bs1-level frequency is candidate-only",
        "clinvar conflict",
        "candidate-only and do not alter classification",
        "pvs1 is candidate-only",
        "opposing pathogenic and benign evidence defaults to vus",
    ]
    for phrase in expected_phrases:
        assert phrase in rationales
