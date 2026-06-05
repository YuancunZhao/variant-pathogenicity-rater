from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from variant_pathogenicity_rater.natural_language_input import rate_variant_from_text
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "real_world_smoke_variants_v1.json"

CANONICAL_FIELDS = {
    "input",
    "variant",
    "runtime",
    "providers",
    "evidence",
    "classification",
    "review",
    "limitations",
}

LEGACY_FIELDS = {
    "final_classification",
    "normalized_variant",
    "variant_resolution",
    "applied_evidence",
    "candidate_evidence",
}

PROVIDER_KEYS = {
    "clinvar",
    "population",
    "computational",
    "literature",
    "clingen_erepo",
    "transcript",
    "vcep",
}


def _dataset() -> dict[str, Any]:
    return json.loads(DATASET_PATH.read_text())


def _cases() -> list[dict[str, Any]]:
    return list(_dataset()["cases"])


def _offline_payload(case: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "gene": case["gene"],
        "transcript": case["transcript"],
        "hgvs_c": case["hgvs_c"],
        "options": {
            "mock_mode": True,
            "include_literature": False,
        },
    }
    if case.get("disease") is not None:
        payload["disease"] = case["disease"]
    if case.get("inheritance") is not None:
        payload["inheritance"] = case["inheritance"]
    return payload


def _online_payload(case: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    payload = _offline_payload(case)
    payload["options"] = {
        **payload["options"],
        "use_online_clinvar": True,
        "use_online_gnomad": True,
        "use_online_vep": True,
        "use_online_pubmed": False,
        "use_online_litvar": False,
        "provider_cache_dir": str(tmp_path / "real-world-online-smoke-cache"),
    }
    return payload


def _provider_outcomes(result: dict[str, Any]) -> dict[str, str]:
    providers = result.get("providers") or {}
    return {
        key: str(value.get("outcome") or "unknown")
        for key, value in providers.items()
        if key in PROVIDER_KEYS and isinstance(value, dict)
    }


def _smoke_stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    provider_counts: dict[str, Counter[str]] = {provider: Counter() for provider in PROVIDER_KEYS}
    unresolved_protein = 0
    unresolved_coordinate = 0
    unresolved_transcript = 0
    normalization_failures = 0
    structured_errors = 0

    for result in results:
        if result.get("status") == "error":
            structured_errors += 1
        if result.get("status") == "error" and result.get("stage") == "normalization":
            normalization_failures += 1
        variant = result.get("variant") or {}
        unresolved = set(variant.get("unresolved_fields") or [])
        placeholders = set(variant.get("placeholder_fields") or [])
        resolution = variant.get("resolution_summary") or {}
        if "hgvs_p" in unresolved or "hgvs_p" in placeholders:
            unresolved_protein += 1
        if {"chrom", "pos", "ref", "alt"} & unresolved or {"hgvs_g", "ref", "alt"} & placeholders:
            unresolved_coordinate += 1
        transcript_provider = (result.get("providers") or {}).get("transcript") or {}
        transcript_limitations = [
            str(item) for item in transcript_provider.get("limitations") or []
        ]
        if transcript_provider.get("outcome") != "success" or any(
            "No transcript resolution fixture matched" in item
            or "No matching local transcript resolution fixture" in item
            for item in transcript_limitations
        ):
            unresolved_transcript += 1
        for provider, outcome in _provider_outcomes(result).items():
            provider_counts[provider][outcome] += 1

    return {
        "total_cases": len(results),
        "ok_cases": sum(1 for result in results if result.get("status") == "ok"),
        "structured_error_cases": structured_errors,
        "normalization_failures": normalization_failures,
        "provider_outcomes": {
            provider: dict(sorted(counter.items()))
            for provider, counter in sorted(provider_counts.items())
        },
        "unresolved_protein_count": unresolved_protein,
        "unresolved_coordinate_count": unresolved_coordinate,
        "unresolved_transcript_count": unresolved_transcript,
    }


def _assert_structured_result(result: dict[str, Any]) -> None:
    assert result["status"] in {"ok", "error"}
    assert CANONICAL_FIELDS.issubset(result)
    assert LEGACY_FIELDS.issubset(result)
    assert isinstance(result["input"], dict)
    assert isinstance(result["variant"], dict)
    assert isinstance(result["runtime"], dict)
    assert isinstance(result["providers"], dict)
    assert isinstance(result["evidence"], dict)
    assert isinstance(result["classification"], dict)
    assert isinstance(result["review"], dict)
    assert isinstance(result["limitations"], list)

    if result["status"] == "ok":
        assert result["final_classification"]
        assert result["classification"]["final_classification"] == result["final_classification"]
    else:
        assert result["limitations"]
        assert result["human_review_required"] is True

    assert result["runtime"]["offline_default_mode"] is True
    assert result["runtime"]["network_policy"]["online_requested"] is False
    assert set(_provider_outcomes(result)) == PROVIDER_KEYS
    assert "evidence_status_summary" in result["evidence"]


def test_real_world_smoke_dataset_shape() -> None:
    dataset = _dataset()
    cases = dataset["cases"]

    assert dataset["dataset_id"] == "real_world_smoke_variants_v1"
    assert len(cases) == 6
    assert len({case["case_id"] for case in cases}) == len(cases)
    for case in cases:
        assert {
            "case_id",
            "original_input",
            "gene",
            "transcript",
            "hgvs_c",
            "disease",
            "inheritance",
            "notes",
        }.issubset(case)
        assert case["original_input"] == f"{case['gene']};{case['hgvs_c']}"
        assert case["hgvs_c"].startswith(f"{case['transcript']}:c.")


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_real_world_hgvs_cases_return_structured_results(case: dict[str, Any]) -> None:
    result = rate_variant(_offline_payload(case))

    _assert_structured_result(result)
    assert result["input"]["original_input"]["gene"] == case["gene"]
    assert result["input"]["original_input"]["transcript"] == case["transcript"]
    assert result["input"]["original_input"]["hgvs_c"] == case["hgvs_c"]
    assert result["providers"]["literature"]["outcome"] == "skipped"
    assert result["evidence"]["applied"] == result["applied_evidence"]
    assert result["evidence"]["candidate"] == result["candidate_evidence"]
    assert result["review"]["human_review_required"] is True


def test_real_world_smoke_summary_is_auditable() -> None:
    results = [rate_variant(_offline_payload(case)) for case in _cases()]
    stats = _smoke_stats(results)

    assert stats["total_cases"] == 6
    assert stats["ok_cases"] + stats["structured_error_cases"] == 6
    assert stats["normalization_failures"] == 0
    assert stats["unresolved_protein_count"] >= 1
    assert stats["unresolved_coordinate_count"] >= 1
    assert stats["unresolved_transcript_count"] >= 1
    assert stats["provider_outcomes"]["population"]["success"] == 6
    assert stats["provider_outcomes"]["clinvar"]["no_record"] == 6
    assert stats["provider_outcomes"]["literature"]["skipped"] == 6


def test_real_world_text_smoke_pklr_does_not_crash() -> None:
    result = rate_variant_from_text(
        "PKLR NM_000298.6:c.1403C>G",
        options={"include_literature": False},
    )

    assert result["status"] in {"ok", "error"}
    assert result["input"]["original_input"]["text"] == "PKLR NM_000298.6:c.1403C>G"
    assert result["input"]["parsed_input"]["gene"] == "PKLR"
    assert result["input"]["parsed_input"]["hgvs_c"] == "NM_000298.6:c.1403C>G"
    assert result["rate_variant_result"] is not None


def test_real_world_online_smoke_is_env_gated(tmp_path: Path) -> None:
    if os.environ.get("VPR_RUN_REAL_WORLD_ONLINE_SMOKE") != "1":
        pytest.skip("Real-world online smoke is opt-in; set VPR_RUN_REAL_WORLD_ONLINE_SMOKE=1.")

    results = [rate_variant(_online_payload(case, tmp_path)) for case in _cases()]
    stats = _smoke_stats(results)

    assert stats["total_cases"] == 6
    assert stats["ok_cases"] + stats["structured_error_cases"] == 6
    for result in results:
        assert result["runtime"]["network_policy"]["online_requested"] is True
        assert _provider_outcomes(result)
