from __future__ import annotations

import json
from pathlib import Path

from variant_pathogenicity_rater.acmg.computational_rules import (
    evaluate_computational_predictions,
)
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.evidence.computational import MockComputationalPredictionProvider
from variant_pathogenicity_rater.schemas import ComputationalPrediction, Variant


ROOT = Path(__file__).resolve().parents[1]


def _load_example(name: str) -> tuple[Variant, list[ComputationalPrediction]]:
    payload = json.loads((ROOT / "examples" / name).read_text())
    return (
        Variant.model_validate(payload["variant"]),
        [
            ComputationalPrediction.model_validate(prediction)
            for prediction in payload["computational_predictions"]
        ],
    )


def test_multiple_pathogenic_predictors_trigger_pp3_supporting_only() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")

    evidence_items, review_flags, summary = evaluate_computational_predictions(
        variant, predictions
    )

    assert review_flags == []
    assert len(evidence_items) == 1
    assert evidence_items[0].code == "PP3"
    assert evidence_items[0].strength == "supporting"
    assert evidence_items[0].direction == "pathogenic"
    assert summary["pathogenic_support_count"] >= 2


def test_multiple_benign_predictors_trigger_bp4_supporting_only() -> None:
    variant, predictions = _load_example("computational_bp4_input.json")

    evidence_items, review_flags, summary = evaluate_computational_predictions(
        variant, predictions
    )

    assert review_flags == []
    assert len(evidence_items) == 1
    assert evidence_items[0].code == "BP4"
    assert evidence_items[0].strength == "supporting"
    assert evidence_items[0].direction == "benign"
    assert summary["benign_support_count"] >= 2


def test_conflicting_predictors_do_not_apply_pp3_or_bp4() -> None:
    variant, predictions = _load_example("computational_conflict_input.json")

    evidence_items, review_flags, summary = evaluate_computational_predictions(
        variant, predictions
    )

    assert evidence_items == []
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_CONFLICT"
    assert summary["pathogenic_support_count"] >= 2
    assert summary["benign_support_count"] >= 2


def test_spliceai_high_score_can_support_pp3_but_not_pvs1_or_ps3() -> None:
    variant, predictions = _load_example("computational_spliceai_pp3_input.json")

    evidence_items, _, _ = evaluate_computational_predictions(variant, predictions)

    assert len(evidence_items) == 1
    assert evidence_items[0].code == "PP3"
    assert "does not replace PVS1 or PS3" in evidence_items[0].reason
    assert evidence_items[0].supporting_data["limitations"] == [
        "PP3/BP4 are applied only at supporting strength.",
        "Computational evidence does not replace functional evidence such as PS3.",
        "SpliceAI splice-related support does not replace PVS1.",
    ]


def test_thresholds_are_configurable() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    thresholds = ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=4)

    evidence_items, review_flags, summary = evaluate_computational_predictions(
        variant, predictions, thresholds
    )

    assert evidence_items == []
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_INSUFFICIENT"
    assert summary["thresholds"]["min_pathogenic_supporting_tools"] == 4


def test_mock_computational_provider_returns_deterministic_predictions() -> None:
    variant, _ = _load_example("computational_pp3_input.json")

    predictions = MockComputationalPredictionProvider().query(variant)

    assert [prediction.method for prediction in predictions] == ["REVEL", "CADD"]
    assert all(prediction.source.name == "mock_computational_predictions" for prediction in predictions)
