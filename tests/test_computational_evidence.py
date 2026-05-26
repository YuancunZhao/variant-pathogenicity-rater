from __future__ import annotations

import json
from pathlib import Path

from variant_pathogenicity_rater.acmg.computational_rules import (
    evaluate_computational_predictions,
)
from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.schemas import EvidenceItem
from variant_pathogenicity_rater.evidence.computational import MockComputationalPredictionProvider
from variant_pathogenicity_rater.schemas import ComputationalPrediction, Transcript, Variant
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.data_sources.provenance import provenance_from_raw_record
from variant_pathogenicity_rater.computational.providers import (
    load_local_computational_file,
    parse_local_computational_record,
)


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
    assert evidence_items[0].candidate_only is True
    assert evidence_items[0].applied is False
    assert "SpliceAI cannot trigger PVS1" in "; ".join(evidence_items[0].supporting_data["limitations"])
    assert "Computational prediction is not functional evidence" in "; ".join(
        evidence_items[0].supporting_data["limitations"]
    )


def test_thresholds_are_configurable() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    thresholds = ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=4)

    evidence_items, review_flags, summary = evaluate_computational_predictions(
        variant, predictions, thresholds
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].candidate_only is True
    assert evidence_items[0].strength == "none"
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_INSUFFICIENT"
    assert summary["thresholds"]["min_pathogenic_supporting_tools"] == 4


def test_mock_computational_provider_returns_deterministic_predictions() -> None:
    variant, _ = _load_example("computational_pp3_input.json")

    predictions = MockComputationalPredictionProvider().query(variant)

    assert [prediction.method for prediction in predictions] == ["REVEL", "CADD"]
    assert all(prediction.source.name == "mock_computational_predictions" for prediction in predictions)


def test_single_predictor_only_is_candidate_only() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")

    evidence_items, review_flags, _ = evaluate_computational_predictions(variant, predictions[:1])

    assert len(evidence_items) == 1
    assert evidence_items[0].code == "PP3"
    assert evidence_items[0].candidate_only is True
    assert evidence_items[0].strength == "none"
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_INSUFFICIENT"


def test_ambiguous_predictor_results_do_not_apply_evidence() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    ambiguous = [
        ComputationalPrediction.model_validate(
            {
                "source": {"name": "mock_REVEL", "version": "fixture-v1"},
                "method": "REVEL",
                "score": 0.4,
                "prediction": "uncertain",
            }
        )
    ]

    evidence_items, review_flags, summary = evaluate_computational_predictions(variant, ambiguous)

    assert evidence_items == []
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_AMBIGUOUS"
    assert summary["consensus_direction"] == "neutral"


def test_missing_predictor_data_produces_no_evidence() -> None:
    variant, _ = _load_example("computational_pp3_input.json")

    evidence_items, review_flags, summary = evaluate_computational_predictions(variant, [])

    assert evidence_items == []
    assert review_flags == []
    assert "No computational predictor data were supplied." in summary["decision"]["limitations"]


def test_low_spliceai_alone_does_not_apply_bp4() -> None:
    variant, _ = _load_example("computational_spliceai_pp3_input.json")
    prediction = ComputationalPrediction.model_validate(
        {
            "source": {"name": "mock_SpliceAI", "version": "fixture-v1"},
            "method": "SpliceAI",
            "score": 0.01,
            "prediction": "no predicted splice impact",
        }
    )

    evidence_items, review_flags, _ = evaluate_computational_predictions(variant, [prediction])

    assert len(evidence_items) == 1
    assert evidence_items[0].code == "BP4"
    assert evidence_items[0].candidate_only is True
    assert evidence_items[0].applied is False
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_INSUFFICIENT"


def test_canonical_splice_high_spliceai_does_not_trigger_ps3_or_pvs1() -> None:
    variant, predictions = _load_example("computational_spliceai_pp3_input.json")
    annotation = _annotation("splice_donor_variant", splice_region=True)

    evidence_items, _, summary = evaluate_computational_predictions(
        variant,
        predictions[:1],
        annotation=annotation,
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].code == "PP3"
    assert all(item.code not in {"PS3", "PVS1", "BS3"} for item in evidence_items)
    assert "SpliceAI cannot trigger PVS1" in "; ".join(summary["decision"]["limitations"])


def test_applied_pvs1_with_splice_computational_adds_double_count_warning() -> None:
    variant, predictions = _load_example("computational_spliceai_pp3_input.json")
    pvs1 = EvidenceItem.model_validate(
        {
            "evidence_id": "ev-pvs1",
            "code": "PVS1",
            "strength": "very_strong",
            "direction": "pathogenic",
            "reason": "Applied PVS1 mock.",
            "source": {"name": "mock"},
            "confidence": 0.8,
            "applied": True,
            "candidate_only": False,
        }
    )

    evidence_items, _, summary = evaluate_computational_predictions(
        variant,
        predictions,
        annotation=_annotation("splice_region_variant", splice_region=True),
        existing_evidence_items=[pvs1],
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].candidate_only is True
    assert summary["decision"]["double_counting_warnings"]


def test_predictor_transcript_mismatch_is_candidate_only() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    variant.transcript = Transcript(accession="NM_004333", version="6", gene_symbol="BRAF")
    mismatched = [
        prediction.model_copy(update={"transcript": "NM_000000.1"})
        for prediction in predictions
    ]

    evidence_items, _, summary = evaluate_computational_predictions(variant, mismatched)

    assert len(evidence_items) == 1
    assert evidence_items[0].candidate_only is True
    assert "Quality check failed: transcript_match." in summary["decision"]["limitations"]


def test_frameshift_with_missense_predictors_is_candidate_limitation() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    variant.hgvs_p = "p.Glu23ValfsTer17"

    evidence_items, _, summary = evaluate_computational_predictions(variant, predictions)

    assert len(evidence_items) == 1
    assert evidence_items[0].candidate_only is True
    assert "Missense computational predictors are not applicable" in "; ".join(
        summary["decision"]["limitations"]
    )


def test_candidate_computational_evidence_does_not_alter_classification() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    candidate_items, _, _ = evaluate_computational_predictions(variant, predictions[:1])

    result = classify_acmg(candidate_items, variant)

    assert result.final_classification == "vus"
    assert not result.pathogenic_evidence_summary


def test_applied_pp3_affects_classification_only_via_combiner() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    pp3_items, _, _ = evaluate_computational_predictions(variant, predictions)
    pvs1 = EvidenceItem.model_validate(
        {
            "evidence_id": "ev-pvs1",
            "code": "PVS1",
            "strength": "very_strong",
            "direction": "pathogenic",
            "reason": "Applied PVS1 mock.",
            "source": {"name": "mock"},
            "confidence": 0.8,
            "applied": True,
            "candidate_only": False,
        }
    )
    pm2 = EvidenceItem.model_validate(
        {
            "evidence_id": "ev-pm2",
            "code": "PM2",
            "strength": "moderate",
            "direction": "pathogenic",
            "reason": "Applied PM2 mock.",
            "source": {"name": "mock"},
            "confidence": 0.8,
            "applied": True,
            "candidate_only": False,
        }
    )

    without_pp3 = classify_acmg([pvs1, pm2], variant)
    with_pp3 = classify_acmg([pvs1, pm2, *pp3_items], variant)

    assert without_pp3.final_classification == "likely_pathogenic"
    assert with_pp3.final_classification == "pathogenic"
    assert pp3_items[0].supporting_data["computational_evidence_decision"]["applied"] is True


def test_decision_summary_contains_reportable_consensus_fields() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")

    evidence_items, _, summary = evaluate_computational_predictions(variant, predictions)

    data = evidence_items[0].supporting_data
    assert data["predictor_summary"]
    assert data["thresholds_used"]
    assert data["quality_checks"]
    assert data["consensus_direction"] == "pathogenic"
    assert summary["conflict_reasons"] == []


def test_cross_group_predictor_conflict_blocks_applied_evidence() -> None:
    variant, predictions = _load_example("computational_pp3_input.json")
    conflicting = [
        predictions[0],
        ComputationalPrediction.model_validate(
            {
                "source": {"name": "mock_SpliceAI", "version": "fixture-v1"},
                "method": "SpliceAI",
                "score": 0.01,
                "prediction": "no predicted splice impact",
                "genome_build": "GRCh38",
            }
        ),
    ]

    evidence_items, review_flags, summary = evaluate_computational_predictions(
        variant,
        conflicting,
        ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=1),
    )

    assert len(evidence_items) == 1
    assert evidence_items[0].candidate_only is True
    assert evidence_items[0].applied is False
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_CONFLICT"
    assert summary["conflict_reasons"]


def test_local_computational_json_record_preserves_supported_fields(tmp_path) -> None:
    path = tmp_path / "computational.json"
    path.write_text(
        json.dumps(
            {
                "gene": "BRAF",
                "transcript": "NM_004333.6",
                "hgvs_p": "p.Val600Glu",
                "protein_change": "V600E",
                "revel_score": 0.91,
                "alphamissense_class": "likely_pathogenic",
                "source_version": "local-v1",
                "genome_build": "GRCh38",
                "provenance": {"snapshot": "unit-test"},
            }
        ),
        encoding="utf-8",
    )

    records = load_local_computational_file(path)
    predictions = parse_local_computational_record(records[0])

    assert len(records) == 1
    assert {prediction.method for prediction in predictions} == {"REVEL", "AlphaMissense"}
    assert all(prediction.hgvs_p == "p.Val600Glu" for prediction in predictions)
    assert all(prediction.protein_change == "V600E" for prediction in predictions)
    assert all(prediction.genome_build == "GRCh38" for prediction in predictions)


def _annotation(consequence: str, *, splice_region: bool = False) -> VariantAnnotation:
    return VariantAnnotation.model_validate(
        {
            "gene": "MSH2",
            "transcript": "NM_000251.3",
            "consequence": consequence,
            "consequence_terms": [consequence],
            "canonical": True,
            "splice_region": splice_region,
            "annotation_source": "test",
            "provenance": provenance_from_raw_record(
                data_source="test",
                source_version="fixture",
                query={},
                raw_record={},
                parser_version="test",
            ).model_dump(mode="json"),
        }
    )
