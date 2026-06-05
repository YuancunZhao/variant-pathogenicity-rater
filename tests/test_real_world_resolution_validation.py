from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.resolution.hgvs_provider import resolve_hgvs_to_variant


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "real_world_smoke_variants_v1.json"

BEFORE_78A_RESOLVED_COUNTS = {
    "hgvs_p": 0,
    "chrom": 0,
    "pos": 0,
    "ref": 5,
    "alt": 5,
    "consequence": 0,
}


def _cases() -> list[dict[str, Any]]:
    return list(json.loads(DATASET_PATH.read_text())["cases"])


def _payload(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "gene": case["gene"],
        "transcript": case["transcript"],
        "hgvs_c": case["hgvs_c"],
        "options": {
            "mock_mode": True,
            "include_literature": False,
        },
    }


def _resolved_fields(result: dict[str, Any]) -> dict[str, bool]:
    resolution = result["variant_resolution"]
    protein = resolution.get("resolved_hgvs_p") or {}
    coordinate = resolution.get("resolved_coordinate") or {}
    return {
        "hgvs_p": bool(protein.get("hgvs_p")),
        "chrom": bool(coordinate.get("chrom")),
        "pos": bool(coordinate.get("pos")),
        "ref": bool(coordinate.get("ref")),
        "alt": bool(coordinate.get("alt")),
        "consequence": bool(protein.get("consequence")),
    }


def test_real_world_resolution_validation_runs_all_cases() -> None:
    results = []
    for case in _cases():
        result = rate_variant(_payload(case))
        results.append(result)

        assert result["status"] == "ok", case["case_id"]
        assert result["variant_resolution"], case["case_id"]
        assert result["variant"]["protein_resolution"] is not None
        assert result["variant"]["coordinate_resolution"] is not None
        assert result["variant"]["resolution_runtime"]["outcome"] in {
            "success",
            "partial",
            "no_record",
            "failure",
            "skipped",
        }
        assert result["classification_result"]["final_classification"] == result["final_classification"]

    after_counts = Counter()
    for result in results:
        for field, resolved in _resolved_fields(result).items():
            if resolved:
                after_counts[field] += 1

    assert after_counts["hgvs_p"] > BEFORE_78A_RESOLVED_COUNTS["hgvs_p"]
    assert after_counts["chrom"] > BEFORE_78A_RESOLVED_COUNTS["chrom"]
    assert after_counts["pos"] > BEFORE_78A_RESOLVED_COUNTS["pos"]
    assert after_counts["consequence"] > BEFORE_78A_RESOLVED_COUNTS["consequence"]


def test_hgvs_resolution_provider_failure_is_limitation_only() -> None:
    result = resolve_hgvs_to_variant(
        gene="GENE1",
        transcript="not a transcript",
        hgvs_c="not-an-hgvs",
    )

    assert result.outcome == "failure"
    assert result.limitations


def test_coordinate_inheritance_preserves_structured_input() -> None:
    result = rate_variant(
        {
            "gene": "GENE1",
            "chromosome": "1",
            "position": 1,
            "ref": "A",
            "alt": "G",
            "hgvs_c": "NM_000001.1:c.1A>G",
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_clinvar": False,
                "include_literature": False,
            },
        }
    )

    coordinate = result["variant_resolution"]["resolved_coordinate"]
    assert coordinate["chrom"] == "1"
    assert coordinate["pos"] == 1
    assert coordinate["ref"] == "A"
    assert coordinate["alt"] == "G"
    assert result["variant"]["coordinate_resolution"] == coordinate
