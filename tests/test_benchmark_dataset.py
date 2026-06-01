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
PHASE_B_START = 41
PHASE_C_START = 71
FIXTURE_PROVIDER_NAMES = {
    "annotation",
    "population",
    "clinvar",
    "computational",
    "literature",
    "clingen_erepo",
    "transcript_metadata",
    "vcep_profile",
}


def _benchmark_cases() -> list[dict[str, Any]]:
    payload = json.loads(BENCHMARK_PATH.read_text())
    return payload["cases"]


def _phase_b_cases() -> list[dict[str, Any]]:
    return [
        case
        for case in _benchmark_cases()
        if int(case["case_id"].split("-", 1)[1]) >= PHASE_B_START
    ]


def _phase_c_cases() -> list[dict[str, Any]]:
    return [
        case
        for case in _benchmark_cases()
        if int(case["case_id"].split("-", 1)[1]) >= PHASE_C_START
    ]


def _case_by_id(case_id: str) -> dict[str, Any]:
    return next(case for case in _benchmark_cases() if case["case_id"] == case_id)


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


def _fixture_id(ref: str) -> tuple[str, str] | None:
    if ":" not in ref or ref.startswith("inline:"):
        return None
    provider, fixture_id = ref.split(":", 1)
    return provider, fixture_id


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
    annotation_records = _fixture_value(case, "annotation")
    transcript_metadata_records = _fixture_value(case, "transcript_metadata")

    options = {
        "mock_mode": True,
        "population_frequency": population,
        "population_thresholds": case["population_thresholds"],
        "computational_predictions": computational_predictions,
        "clinvar_records": clinvar_records,
        "literature_records": literature_records,
        "mock_supplemental_evidence_items": case["mock_applied_evidence"],
    }
    if annotation_records is not None:
        options["annotation_records"] = annotation_records
    if transcript_metadata_records is not None:
        options["transcript_metadata_records"] = transcript_metadata_records
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


def _evidence_sources_by_code(items: list[dict[str, Any]], code: str) -> set[str]:
    return {
        item.get("source", {}).get("name", "")
        for item in items
        if item["code"] == code and item.get("source", {}).get("name")
    }


def _evidence_by_code(items: list[dict[str, Any]], code: str) -> list[dict[str, Any]]:
    return [item for item in items if item["code"] == code]


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
        assert isinstance(case["expected_applied_evidence"], list), case["case_id"]
        assert isinstance(case["expected_candidate_evidence"], list), case["case_id"]


def test_benchmark_case_ids_are_unique_stable_and_manifest_count_matches() -> None:
    payload = json.loads(BENCHMARK_PATH.read_text())
    cases = payload["cases"]
    case_ids = [case["case_id"] for case in cases]

    assert payload["case_count"] == len(cases)
    assert len(case_ids) == len(set(case_ids))
    assert case_ids == [f"bench-{index:02d}" for index in range(1, len(cases) + 1)]


def test_phase_b_cases_have_purpose_category_and_strict_expectations() -> None:
    for case in _phase_b_cases():
        assert case.get("case_category"), case["case_id"]
        assert case.get("safety_focus"), case["case_id"]
        assert case.get("rationale"), case["case_id"]
        assert case.get("variant_input"), case["case_id"]
        assert case.get("disease_context"), case["case_id"]
        assert isinstance(case.get("expected_applied_evidence"), list), case["case_id"]
        assert isinstance(case.get("expected_candidate_evidence"), list), case["case_id"]
        assert "expected_limitations" in case, case["case_id"]


def test_phase_b_provider_fixture_refs_resolve_and_do_not_cross_pollute() -> None:
    for case in _phase_b_cases():
        refs = case.get("provider_fixture_refs") or {}
        assert {"population", "clinvar", "computational", "literature"}.issubset(refs), case["case_id"]
        for provider_name, ref in refs.items():
            assert provider_name in FIXTURE_PROVIDER_NAMES, (case["case_id"], provider_name)
            parsed = _fixture_id(str(ref))
            assert parsed is not None, (case["case_id"], provider_name, ref)
            fixture_provider, fixture_id = parsed
            assert fixture_provider == provider_name, (case["case_id"], provider_name, ref)
            assert fixture_id == case["case_id"], (case["case_id"], provider_name, ref)
            assert fixture_id in _fixture_records(fixture_provider), (case["case_id"], provider_name, ref)


def test_no_unused_phase_b_fixture_rows() -> None:
    used: dict[str, set[str]] = {name: set() for name in FIXTURE_PROVIDER_NAMES}
    for case in _phase_b_cases():
        for ref in (case.get("provider_fixture_refs") or {}).values():
            parsed = _fixture_id(str(ref))
            if parsed is None:
                continue
            provider_name, fixture_id = parsed
            used[provider_name].add(fixture_id)

    for provider_name in FIXTURE_PROVIDER_NAMES:
        fixture_ids = set(_fixture_records(provider_name))
        assert fixture_ids == used[provider_name], provider_name


def test_reviewed_evidence_cases_preserve_source_links_and_apply_only_when_reviewed() -> None:
    for case in _benchmark_cases():
        reviewed = case.get("reviewed_evidence") or []
        if not reviewed:
            continue

        result = rate_variant(_pipeline_payload(case))
        applied_items = [item for item in result["evidence_items"] if not _is_candidate(item)]
        candidate_items = [item for item in result["evidence_items"] if _is_candidate(item)]

        for record in reviewed:
            source_id = record.get("source_candidate_evidence_id")
            status = record["evidence_status"]
            code = record["acmg_code"]
            if source_id:
                assert any(
                    item.get("evidence_id") == source_id
                    or item.get("supporting_data", {}).get("source_candidate_evidence_id") == source_id
                    for item in candidate_items + applied_items
                ), (case["case_id"], source_id)
            if status == "reviewed_applied":
                assert "manual_reviewed_evidence" in _evidence_sources_by_code(applied_items, code)
            else:
                assert "manual_reviewed_evidence" not in _evidence_sources_by_code(applied_items, code)
                assert "manual_reviewed_evidence" in _evidence_sources_by_code(candidate_items, code)


def test_erepo_cases_keep_erepo_evidence_review_note_only() -> None:
    erepo_cases = [
        case for case in _benchmark_cases()
        if (case.get("provider_fixture_refs") or {}).get("clingen_erepo")
        or case.get("options_overrides", {}).get("include_clingen_erepo")
    ]
    assert erepo_cases

    for case in erepo_cases:
        result = rate_variant(_pipeline_payload(case))
        applied_items = [item for item in result["evidence_items"] if not _is_candidate(item)]
        candidate_items = [item for item in result["evidence_items"] if _is_candidate(item)]

        assert not any(item["source"]["name"] == "ClinGen Evidence Repository" for item in applied_items)
        assert any(item["source"]["name"] == "ClinGen Evidence Repository" for item in candidate_items)
        assert result["clingen_erepo_reviewed_evidence_drafts"]
        assert all(
            draft["evidence_status"] != "reviewed_applied"
            for draft in result["clingen_erepo_reviewed_evidence_drafts"]
        )


def test_vcep_signal_only_cases_do_not_change_classification_or_evidence() -> None:
    signal_cases = [
        case
        for case in _benchmark_cases()
        if "VCEP signal-only no classification change" in case.get("safety_focus", [])
    ]
    assert signal_cases

    for case in signal_cases:
        with_signal = rate_variant(_pipeline_payload(case))
        without_signal_case = json.loads(json.dumps(case))
        refs = without_signal_case.get("provider_fixture_refs") or {}
        refs.pop("vcep_profile", None)
        overrides = without_signal_case.get("options_overrides") or {}
        overrides.pop("vcep_profile_records", None)
        overrides["include_vcep_signals"] = False
        overrides["apply_vcep_overrides"] = False
        without_signal_case["options_overrides"] = overrides
        without_signal = rate_variant(_pipeline_payload(without_signal_case))

        assert with_signal["final_classification"] == without_signal["final_classification"]
        assert _codes(with_signal["applied_evidence"]) == _codes(without_signal["applied_evidence"])


def test_phase_c_cases_cover_planned_edge_categories() -> None:
    cases = _phase_c_cases()
    assert len(cases) == 30
    assert [case["case_id"] for case in cases] == [f"bench-{index:02d}" for index in range(71, 101)]

    categories = {case["case_category"] for case in cases}
    assert {
        "pvs1_edge",
        "splice_edge",
        "transcript_mismatch",
        "population_edge",
        "computational_edge",
        "clinvar_ps1_pm5",
        "erepo_vcep",
    }.issubset(categories)


def test_phase_c_pvs1_population_and_computational_boundaries() -> None:
    for case_id in ["bench-72", "bench-73", "bench-74", "bench-75", "bench-76", "bench-77", "bench-89", "bench-90", "bench-100"]:
        result = rate_variant(_pipeline_payload(_case_by_id(case_id)))
        applied = [item for item in result["evidence_items"] if not _is_candidate(item)]
        candidates = [item for item in result["evidence_items"] if _is_candidate(item)]
        assert not _evidence_by_code(applied, "PVS1"), case_id
        assert _evidence_by_code(candidates, "PVS1"), case_id

    last_exon = rate_variant(_pipeline_payload(_case_by_id("bench-71")))
    pvs1_items = _evidence_by_code(last_exon["applied_evidence"], "PVS1")
    assert pvs1_items and pvs1_items[0]["strength"] == "supporting"

    assert _case_by_id("bench-78")["expected_applied_evidence"] == []
    assert _case_by_id("bench-78")["expected_candidate_evidence"] == [{"code": "BA1", "strength": "none"}]
    assert _case_by_id("bench-79")["expected_applied_evidence"] == [{"code": "BA1", "strength": "stand_alone"}]
    assert {"LOW_COVERAGE_POPULATION_FREQUENCY"}.issubset(set(_case_by_id("bench-80")["expected_review_flags"]))
    assert {"POPULATION_MATCH_UNCONFIRMED", "POPULATION_MISMATCH_WARNING"}.issubset(set(_case_by_id("bench-81")["expected_review_flags"]))
    assert {"FOUNDER_VARIANT_WARNING"}.issubset(set(_case_by_id("bench-82")["expected_review_flags"]))
    assert {"CONTEXT_PROVIDER_GENOME_BUILD_VS_INPUT_GENOME_BUILD"}.issubset(set(_case_by_id("bench-83")["expected_review_flags"]))

    for case_id in ["bench-87", "bench-88"]:
        case = _case_by_id(case_id)
        assert not any(item["code"] in {"PP3", "BP4"} for item in case["expected_applied_evidence"])
        assert "COMPUTATIONAL_PREDICTION_CONFLICT" in case["expected_review_flags"]

    splice_high = _case_by_id("bench-89")
    assert {"PVS1", "PP3"} == {item["code"] for item in splice_high["expected_candidate_evidence"]}
    splice_low = _case_by_id("bench-90")
    assert {"PVS1", "PM2", "BP4"} == {item["code"] for item in splice_low["expected_candidate_evidence"]}


def test_phase_c_clinvar_erepo_vcep_and_reviewed_boundaries() -> None:
    ps1 = _case_by_id("bench-91")
    assert {"PS1", "PS3"}.issubset({item["code"] for item in ps1["expected_applied_evidence"]})
    assert ps1["expected_candidate_evidence"] == [{"code": "PP5", "strength": "none"}]

    assert not any(item["code"] in {"PS1", "PM5"} for item in _case_by_id("bench-92")["expected_applied_evidence"])
    assert not any(item["code"] == "PS1" for item in _case_by_id("bench-93")["expected_applied_evidence"])
    assert any(item["code"] == "PM5" for item in _case_by_id("bench-94")["expected_applied_evidence"])
    assert any(item["code"] == "PM5" for item in _case_by_id("bench-95")["expected_candidate_evidence"])
    assert not any(item["code"] in {"PS1", "PM5"} for item in _case_by_id("bench-96")["expected_applied_evidence"])

    erepo_result = rate_variant(_pipeline_payload(_case_by_id("bench-97")))
    erepo_applied = [item for item in erepo_result["evidence_items"] if not _is_candidate(item)]
    erepo_candidates = [item for item in erepo_result["evidence_items"] if _is_candidate(item)]
    assert "ClinGen Evidence Repository" not in _source_names(erepo_applied)
    assert "ClinGen Evidence Repository" in _source_names(erepo_candidates)

    vcep_ba1 = rate_variant(_pipeline_payload(_case_by_id("bench-99")))
    ba1 = next(item for item in vcep_ba1["applied_evidence"] if item["code"] == "BA1")
    assert ba1["supporting_data"]["vcep_override"]["override_applied"] is True

    vcep_pvs1_disabled = rate_variant(_pipeline_payload(_case_by_id("bench-100")))
    pvs1 = next(item for item in vcep_pvs1_disabled["review_note_evidence"] if item["code"] == "PVS1")
    assert pvs1["supporting_data"]["vcep_override"]["override_applied_to_item"] is False

    reviewed_applied_sources = {
        item["source"]["name"]
        for case_id in ["bench-85", "bench-91", "bench-94"]
        for item in rate_variant(_pipeline_payload(_case_by_id(case_id)))["applied_evidence"]
    }
    assert "manual_reviewed_evidence" in reviewed_applied_sources


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
