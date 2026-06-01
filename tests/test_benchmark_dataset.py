from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


BENCHMARK_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmark_snv_cases.json"
FIXTURE_DIR = BENCHMARK_PATH.parent / "benchmark_provider_fixtures"
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


@lru_cache(maxsize=None)
def _fixture_records(name: str) -> dict[str, Any]:
    path = FIXTURE_DIR / f"{name}.jsonl"
    if not path.exists():
        return {}
    records: dict[str, Any] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records[payload["fixture_id"]] = payload["record"]
    return records


def _fixture_ref(case: dict[str, Any], name: str) -> str | None:
    refs = case.get("provider_fixture_refs") or {}
    ref = refs.get(name)
    return str(ref) if ref else None


def _fixture_value(case: dict[str, Any], name: str) -> Any | None:
    ref = _fixture_ref(case, name)
    if not ref:
        return None
    if not ref.startswith(f"{name}:"):
        return None
    fixture_id = ref.split(":", 1)[1]
    return _fixture_records(name).get(fixture_id)


def _variant_id(case: dict[str, Any]) -> str:
    genomic = case["genomic"]
    return (
        f"{genomic.get('genome_build', 'GRCh38')}-"
        f"{genomic['chromosome']}-{genomic['position']}-"
        f"{genomic['ref']}-{genomic['alt']}"
    )


def _pipeline_payload(case: dict[str, Any]) -> dict[str, Any]:
    genomic = case["genomic"]
    population = dict(_fixture_value(case, "population") or case["mock_population_data"])
    if population.get("variant_id") != "__omit__":
        population.setdefault("variant_id", _variant_id(case))
    else:
        population.pop("variant_id")

    clinvar_records = _fixture_value(case, "clinvar") or [case["mock_clinvar_record"]]
    computational_predictions = (
        _fixture_value(case, "computational")
        if _fixture_value(case, "computational") is not None
        else case["mock_computational_prediction"]
    )
    literature_records = (
        _fixture_value(case, "literature")
        if _fixture_value(case, "literature") is not None
        else case["mock_literature_evidence"]
    )

    options = {
        "mock_mode": True,
        "population_frequency": population,
        "population_thresholds": case["population_thresholds"],
        "computational_predictions": computational_predictions,
        "clinvar_records": clinvar_records,
        "literature_records": literature_records,
        "mock_supplemental_evidence_items": case["mock_applied_evidence"],
    }
    erepo_records = _fixture_value(case, "clingen_erepo")
    if erepo_records is not None:
        options["include_clingen_erepo"] = True
        options["clingen_erepo_records"] = erepo_records
    vcep_profiles = _fixture_value(case, "vcep_profile")
    if vcep_profiles is not None:
        options["include_vcep_signals"] = True
        options["vcep_profile_records"] = vcep_profiles
    options.update(case.get("options_overrides", {}))

    payload = {
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
        "options": options,
    }
    if "reviewed_evidence" in case:
        payload["reviewed_evidence"] = case["reviewed_evidence"]
    return payload


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


def _code_strengths(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return sorted(
        [{"code": item["code"], "strength": item["strength"]} for item in items],
        key=lambda item: (item["code"], item["strength"]),
    )


def _review_flag_codes(result: dict[str, Any]) -> set[str]:
    codes = {flag["code"] for flag in result["classification_result"]["review_flags"]}
    for item in result["evidence_items"]:
        codes.update(flag["code"] for flag in item.get("review_flags", []))
    for step in result["step_results"].values():
        if isinstance(step, dict):
            codes.update(flag["code"] for flag in step.get("review_flags", []))
    return codes


def _expected_codes(expected: list[Any]) -> list[str]:
    return sorted(item["code"] if isinstance(item, dict) else item for item in expected)


def _expected_code_strengths(expected: list[Any]) -> list[dict[str, str]] | None:
    if not expected or not all(isinstance(item, dict) for item in expected):
        return None
    return sorted(
        [{"code": item["code"], "strength": item["strength"]} for item in expected],
        key=lambda item: (item["code"], item["strength"]),
    )


def _source_names(items: list[dict[str, Any]]) -> set[str]:
    return {
        item.get("source", {}).get("name", "")
        for item in items
        if item.get("source", {}).get("name")
    }


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
        "expected_limitations",
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
    assert _codes(applied_items) == _expected_codes(case["expected_applied_evidence"])
    assert _codes(candidate_items) == _expected_codes(case["expected_candidate_evidence"])
    expected_applied_strengths = _expected_code_strengths(case["expected_applied_evidence"])
    if expected_applied_strengths is not None:
        assert _code_strengths(applied_items) == expected_applied_strengths
    expected_candidate_strengths = _expected_code_strengths(case["expected_candidate_evidence"])
    if expected_candidate_strengths is not None:
        assert _code_strengths(candidate_items) == expected_candidate_strengths

    review_codes = _review_flag_codes(result)
    assert set(case["expected_review_flags"]).issubset(review_codes)
    for limitation in case.get("expected_limitations", []):
        assert any(limitation in actual for actual in result["limitations"]), limitation
    if case.get("expected_provenance_sources"):
        sources = _source_names(result["evidence_items"])
        assert set(case["expected_provenance_sources"]).issubset(sources)
    for step_name in case.get("expected_step_results", []):
        assert step_name in result["step_results"]

    report_text = result["report_text"]
    assert "## Applied ACMG Evidence" in report_text
    assert "## Candidate / Review-Note Evidence" in report_text
    applied_section = _section(
        report_text,
        "## Applied ACMG Evidence",
        "## Candidate / Review-Note Evidence",
    )
    candidate_section = _section(
        report_text,
        "## Candidate / Review-Note Evidence",
        "## Conflicting Evidence",
    )
    for code in _expected_codes(case["expected_applied_evidence"]):
        assert f": {code} /" in applied_section
    for code in _expected_codes(case["expected_candidate_evidence"]):
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
        "applied ps1",
        "applied pm5",
        "reviewed_applied pm3",
        "draft vcep profile is signal-only",
        "disables pp3",
        "clinvar conflict",
        "literature-suggested ps3 draft stays needs_more_info",
        "clingen erepo exact variant match is review-note only",
    ]
    for phrase in expected_phrases:
        assert phrase in rationales
