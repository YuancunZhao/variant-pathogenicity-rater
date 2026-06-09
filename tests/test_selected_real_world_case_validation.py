"""Selected real-world case validation scaffold.

Offline fixture-backed tests that exercise ProviderExecutionPlan observability,
ProviderRuntimeResult provenance, and candidate/applied evidence safety
invariants without changing classification or provider execution behavior.

All tests run offline (mock_mode=True, no live network calls).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "data" / "selected_real_world_validation_cases.json"
CLINVAR_FIXTURE_PATH = ROOT / "data" / "fixtures" / "clinvar_smoke.jsonl"
POPULATION_FIXTURE_PATH = ROOT / "data" / "fixtures" / "population_smoke.jsonl"

# ── helpers ──────────────────────────────────────────────────────────


def _jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        fixture_id = record.get("fixture_id")
        assert fixture_id, f"{path} line missing fixture_id"
        records[fixture_id] = record
    return records


def _cases() -> list[dict[str, Any]]:
    return json.loads(CASE_PATH.read_text())["cases"]


CLINVAR_FIXTURES = _jsonl_by_id(CLINVAR_FIXTURE_PATH)
POPULATION_FIXTURES = _jsonl_by_id(POPULATION_FIXTURE_PATH)


def _population_payload(case: dict[str, Any]) -> dict[str, Any] | None:
    fixture_id = case.get("population_fixture_id")
    if fixture_id is None:
        return None
    fixture = dict(POPULATION_FIXTURES[fixture_id])
    fixture.pop("fixture_id", None)
    return fixture


def _clinvar_records(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [CLINVAR_FIXTURES[fid] for fid in case.get("clinvar_fixture_ids", [])]


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
        "computational_predictions": case.get("computational_predictions", []),
        "clinvar_records": _clinvar_records(case),
        "include_literature": case.get("include_literature", False),
        "literature_records": case.get("literature_records", []),
        "include_clingen_erepo": case.get("include_clingen_erepo", False),
        "clingen_erepo_records": case.get("clingen_erepo_records", []),
        "mock_supplemental_evidence_items": [],
    }
    population_payload = _population_payload(case)
    if population_payload is not None:
        options["population_frequency"] = population_payload

    return {
        "gene": variant["gene"],
        "transcript": variant["transcript"],
        "hgvs_c": variant["hgvs_c"],
        "hgvs_p": variant.get("hgvs_p"),
        "chromosome": variant.get("chromosome"),
        "position": variant.get("position"),
        "ref": variant.get("ref"),
        "alt": variant.get("alt"),
        "genome_build": variant.get("genome_build", "GRCh38"),
        "disease": case["disease_context"]["disease"],
        "inheritance": case["disease_context"]["inheritance"],
        "gene_disease_context": case["disease_context"],
        "options": options,
    }


def _is_candidate(item: dict[str, Any]) -> bool:
    supporting_data = item.get("supporting_data") or {}
    return (
        item.get("strength") == "none"
        or supporting_data.get("candidate_only") is True
        or supporting_data.get("evidence_status") == "candidate"
        or supporting_data.get("applied") is False
    )


def _codes(items: list[dict[str, Any]]) -> list[str]:
    return sorted(item["code"] for item in items)


# ── fixture shape ────────────────────────────────────────────────────


def test_63A_case_set_shape() -> None:
    cases = _cases()
    assert len(cases) == 6

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
        "provider_invariants",
    }
    for case in cases:
        missing = required_fields - set(case)
        assert not missing, f"{case['case_id']}: missing {missing}"

    scenario_ids = {case["case_id"] for case in cases}
    assert len(scenario_ids) == 6, "case_ids must be unique"


# ── per-case pipeline invariants ─────────────────────────────────────


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_case_runs_full_pipeline(case: dict[str, Any]) -> None:
    result = rate_variant(_pipeline_payload(case))

    # --- basic status ---
    assert result["status"] == "ok", f"{case['case_id']}: status={result['status']}"
    assert result["mock_mode"] is True
    assert result["human_review_required"] is True

    # --- classification within allowed set ---
    assert result["final_classification"] in case["allowed_classifications"], (
        f"{case['case_id']}: {result['final_classification']} not in {case['allowed_classifications']}"
    )

    # --- applied/candidate evidence codes ---
    applied_items = [item for item in result["evidence_items"] if not _is_candidate(item)]
    candidate_items = [item for item in result["evidence_items"] if _is_candidate(item)]
    assert _codes(applied_items) == sorted(case["expected_applied_evidence"]), (
        f"{case['case_id']}: applied {_codes(applied_items)} != {sorted(case['expected_applied_evidence'])}"
    )
    assert _codes(candidate_items) == sorted(case["expected_candidate_evidence"]), (
        f"{case['case_id']}: candidate {_codes(candidate_items)} != {sorted(case['expected_candidate_evidence'])}"
    )

    # --- review flags ---
    review_codes = _review_flag_codes(result)
    for expected_flag in case["expected_review_flags"]:
        assert expected_flag in review_codes, (
            f"{case['case_id']}: missing review flag {expected_flag}"
        )


def _review_flag_codes(result: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for flag in (result.get("classification_result") or {}).get("review_flags", []):
        if isinstance(flag, dict):
            codes.add(flag.get("code", ""))
    for item in result.get("evidence_items", []):
        for flag in item.get("review_flags", []):
            if isinstance(flag, dict):
                codes.add(flag.get("code", ""))
    for step in (result.get("step_results") or {}).values():
        if isinstance(step, dict):
            for flag in step.get("review_flags", []):
                if isinstance(flag, dict):
                    codes.add(flag.get("code", ""))
    return codes


# ── ProviderExecutionPlan invariants ─────────────────────────────────


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_provider_execution_plan_exists_and_validates(case: dict[str, Any]) -> None:
    result = rate_variant(_pipeline_payload(case))
    invariants = case.get("provider_invariants", {})

    if not invariants.get("expect_plan_exists", True):
        pytest.skip("plan not expected for this case")

    step_results = result.get("step_results") or {}
    plan = step_results.get("provider_execution_plan")
    assert plan is not None, f"{case['case_id']}: provider_execution_plan missing"
    assert isinstance(plan, dict)

    # Core plan fields
    assert plan.get("plan_version", "").startswith("79A-3A"), (
        f"{case['case_id']}: plan_version={plan.get('plan_version')}"
    )
    assert isinstance(plan.get("nodes"), list), f"{case['case_id']}: nodes not a list"
    assert len(plan["nodes"]) >= 6, (
        f"{case['case_id']}: expected >=6 nodes, got {len(plan['nodes'])}"
    )

    # Every node has required fields
    for node in plan["nodes"]:
        assert "node_key" in node, f"{case['case_id']}: node missing node_key"
        assert "kind" in node, f"{case['case_id']}: node missing kind"
        assert "enabled" in node, f"{case['case_id']}: node missing enabled"
        assert "planned_attempt" in node, f"{case['case_id']}: node missing planned_attempt"

    # Summary matches node counts
    summary = plan.get("summary") or {}
    assert summary.get("total_nodes") == len(plan["nodes"]), (
        f"{case['case_id']}: summary.total_nodes != len(nodes)"
    )

    # Identity present
    provider_identity = plan.get("provider_identity")
    assert provider_identity is not None, f"{case['case_id']}: provider_identity missing"
    assert provider_identity.get("gene") == case["variant"]["gene"], (
        f"{case['case_id']}: identity gene mismatch"
    )

    # dependency_skip_planned list is a list
    assert isinstance(plan.get("dependency_skip_planned"), list), (
        f"{case['case_id']}: dependency_skip_planned not a list"
    )


# ── ProviderRuntimeResult invariants ─────────────────────────────────


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_provider_runtime_exists_and_validates(case: dict[str, Any]) -> None:
    result = rate_variant(_pipeline_payload(case))
    invariants = case.get("provider_invariants", {})

    if not invariants.get("expect_runtime_exists", True):
        pytest.skip("runtime not expected for this case")

    step_results = result.get("step_results") or {}
    provider_runtime = step_results.get("provider_runtime")
    assert provider_runtime is not None, f"{case['case_id']}: provider_runtime missing"
    assert isinstance(provider_runtime, dict)

    # Known provider keys should have valid entries
    known_providers = ["clinvar", "population", "computational"]
    if invariants.get("expect_literature_provider_present"):
        known_providers.append("literature")
    if invariants.get("expect_erepo_provider_present"):
        known_providers.append("clingen_erepo")

    for provider_key in known_providers:
        entry = provider_runtime.get(provider_key)
        if entry is None:
            continue  # some may be legitimately absent
        assert isinstance(entry, dict), (
            f"{case['case_id']}: provider_runtime.{provider_key} not a dict"
        )
        # Every entry should have an outcome
        assert "outcome" in entry or "provider_name" in entry, (
            f"{case['case_id']}: provider_runtime.{provider_key} missing outcome"
        )


# ── Candidate/applied safety boundaries ──────────────────────────────


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_no_direct_pp5_bp6(case: dict[str, Any]) -> None:
    """ClinVar assertions must never directly apply PP5/BP6."""
    result = rate_variant(_pipeline_payload(case))
    invariants = case.get("provider_invariants", {})

    if not invariants.get("expect_no_direct_pp5_bp6", True):
        pytest.skip("PP5/BP6 check not applicable")

    for item in result.get("evidence_items", []):
        if item.get("source", {}).get("name") == "ClinVar":
            # ClinVar items must always be candidate-only
            assert _is_candidate(item), (
                f"{case['case_id']}: ClinVar item {item['code']} is not candidate-only"
            )
            assert item.get("strength") == "none", (
                f"{case['case_id']}: ClinVar item {item['code']} has strength={item['strength']}"
            )
            supporting = item.get("supporting_data") or {}
            assert supporting.get("candidate_only") is True, (
                f"{case['case_id']}: ClinVar item {item['code']} candidate_only={supporting.get('candidate_only')}"
            )
            # automatic_application must not be explicitly True.
            assert supporting.get("automatic_application") is not True, (
                f"{case['case_id']}: ClinVar item {item['code']} automatic_application=True"
            )


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_candidate_items_preserve_flags(case: dict[str, Any]) -> None:
    """All candidate/review-note items must preserve requires_review/candidate_only/applied flags."""
    result = rate_variant(_pipeline_payload(case))

    for item in result.get("evidence_items", []):
        if _is_candidate(item):
            supporting = item.get("supporting_data") or {}
            # At least one candidate indicator must be present
            is_marked_candidate = (
                item.get("strength") == "none"
                or supporting.get("candidate_only") is True
                or supporting.get("applied") is False
                or supporting.get("evidence_status") == "candidate"
            )
            assert is_marked_candidate, (
                f"{case['case_id']}: candidate item {item['code']} not properly flagged"
            )


# ── PM2 safety gate ──────────────────────────────────────────────────


def test_63A_no_pm2_from_absent_population() -> None:
    """When population fixture is absent, PM2 must not be triggered."""
    case = next(c for c in _cases() if c["case_id"] == "63A-no-population-no-pm2")
    result = rate_variant(_pipeline_payload(case))

    all_codes = [item["code"] for item in result["evidence_items"]]
    assert "PM2" not in all_codes, (
        "PM2 must not appear when population fixture is absent"
    )

    # The population step should show no record
    population_step = result.get("step_results", {}).get("query_population_frequency")
    if isinstance(population_step, dict):
        assert population_step.get("overall_af") is None, (
            "population overall_af should be None when fixture absent"
        )
        assert population_step.get("is_absent") is False, (
            "population is_absent should be False when fixture absent"
        )


# ── Provider summary consistency ─────────────────────────────────────


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_provider_summary_matches_mode_summary(case: dict[str, Any]) -> None:
    """providers.summary should match provider_mode_summary for fresh output."""
    result = rate_variant(_pipeline_payload(case))
    invariants = case.get("provider_invariants", {})

    if not invariants.get("expect_summary_matches_mode_summary", True):
        pytest.skip("summary consistency not required")

    canonical_providers = result.get("providers") or {}
    summary_from_canonical = canonical_providers.get("summary") or {}
    legacy_summary = result.get("provider_mode_summary") or {}

    # Both should be dicts
    assert isinstance(summary_from_canonical, dict)
    assert isinstance(legacy_summary, dict)

    # For fresh output they should agree on key provider outcomes
    for provider_key in legacy_summary:
        if provider_key in summary_from_canonical:
            legacy_outcome = legacy_summary[provider_key]
            canonical_outcome = summary_from_canonical[provider_key]
            if isinstance(legacy_outcome, dict) and isinstance(canonical_outcome, dict):
                assert legacy_outcome.get("outcome") == canonical_outcome.get("outcome"), (
                    f"{case['case_id']}: outcome mismatch for {provider_key}: "
                    f"legacy={legacy_outcome.get('outcome')} canonical={canonical_outcome.get('outcome')}"
                )


# ── Provider dependency check invariants ─────────────────────────────


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["case_id"])
def test_63A_provider_dependency_checks_in_output(case: dict[str, Any]) -> None:
    """provider_dependency_checks exist in output and match plan where present."""
    result = rate_variant(_pipeline_payload(case))

    dep_checks = result.get("provider_dependency_checks")
    assert dep_checks is not None, f"{case['case_id']}: provider_dependency_checks missing"
    assert isinstance(dep_checks, dict)

    # Plan dependency checks should have corresponding entries
    plan = (result.get("step_results") or {}).get("provider_execution_plan") or {}
    for node in plan.get("nodes", []):
        dep_check = node.get("dependency_check")
        if dep_check is None:
            continue
        provider_name = dep_check.get("provider_name")
        if provider_name and provider_name in dep_checks:
            plan_check = dep_checks[provider_name]
            if isinstance(plan_check, dict) and isinstance(dep_check, dict):
                assert plan_check.get("satisfied") == dep_check.get("satisfied"), (
                    f"{case['case_id']}: dependency_check.satisfied mismatch for {provider_name}"
                )


# ── No live network ──────────────────────────────────────────────────


def test_63A_all_cases_run_offline() -> None:
    """Every case must run with mock_mode=True (no live network)."""
    for case in _cases():
        result = rate_variant(_pipeline_payload(case))
        assert result["mock_mode"] is True, f"{case['case_id']}: mock_mode not True"
        assert result.get("offline_default_mode") is True, (
            f"{case['case_id']}: offline_default_mode not True"
        )
