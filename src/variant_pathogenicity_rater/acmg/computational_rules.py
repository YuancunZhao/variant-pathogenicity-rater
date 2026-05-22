from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.evidence.computational import (
    PredictionDirection,
    PredictorCall,
    interpret_prediction,
)
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import Variant


def evaluate_computational_predictions(
    variant: Variant,
    predictions: list[ComputationalPrediction],
    thresholds: ComputationalEvidenceThresholds | None = None,
) -> tuple[list[EvidenceItem], list[ReviewFlag], dict[str, Any]]:
    thresholds = thresholds or ComputationalEvidenceThresholds()
    calls = [interpret_prediction(prediction, thresholds) for prediction in predictions]
    pathogenic_calls = _unique_directional_calls(calls, PredictionDirection.PATHOGENIC)
    benign_calls = _unique_directional_calls(calls, PredictionDirection.BENIGN)
    neutral_calls = [call for call in calls if call.direction == PredictionDirection.NEUTRAL]
    review_flags: list[ReviewFlag] = []

    splice_conflict = _splice_prediction_conflict(calls)
    if splice_conflict:
        review_flags.append(
            ReviewFlag(
                code="SPLICEAI_PREDICTION_CONFLICT",
                message=(
                    "SpliceAI splice prediction is internally conflicting or conflicts with "
                    "other computational calls; PP3/BP4 were not applied."
                ),
                severity="warning",
                blocking=False,
            )
        )
        return [], review_flags, _summary(calls, thresholds)

    pathogenic_met = len(pathogenic_calls) >= thresholds.min_pathogenic_supporting_tools
    benign_met = len(benign_calls) >= thresholds.min_benign_supporting_tools

    if pathogenic_met and benign_met:
        review_flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_CONFLICT",
                message="Computational predictors support both PP3 and BP4; neither criterion was applied.",
                severity="warning",
                blocking=False,
            )
        )
        return [], review_flags, _summary(calls, thresholds)

    if pathogenic_met:
        return [
            _evidence_item(
                variant=variant,
                code=EvidenceCode.PP3,
                direction=EvidenceDirection.PATHOGENIC,
                reason=_pp3_reason(pathogenic_calls),
                calls=pathogenic_calls,
                all_calls=calls,
                predictions=predictions,
            )
        ], review_flags, _summary(calls, thresholds)

    if benign_met:
        return [
            _evidence_item(
                variant=variant,
                code=EvidenceCode.BP4,
                direction=EvidenceDirection.BENIGN,
                reason="Multiple computational methods support no impact on gene or gene product.",
                calls=benign_calls,
                all_calls=calls,
                predictions=predictions,
            )
        ], review_flags, _summary(calls, thresholds)

    if pathogenic_calls and benign_calls:
        review_flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_MIXED",
                message="Computational predictors are mixed below application thresholds; PP3/BP4 not applied.",
                severity="info",
                blocking=False,
            )
        )
    elif pathogenic_calls or benign_calls or neutral_calls:
        review_flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_INSUFFICIENT",
                message="Computational predictors did not meet configured agreement thresholds.",
                severity="info",
                blocking=False,
            )
        )

    return [], review_flags, _summary(calls, thresholds)


def _unique_directional_calls(
    calls: list[PredictorCall],
    direction: PredictionDirection,
) -> list[PredictorCall]:
    seen: set[str] = set()
    selected: list[PredictorCall] = []
    for call in calls:
        if call.direction != direction or call.method in seen:
            continue
        seen.add(call.method)
        selected.append(call)
    return selected


def _splice_prediction_conflict(calls: list[PredictorCall]) -> bool:
    splice_calls = [call for call in calls if call.splice_related]
    if not splice_calls:
        return False
    if any("conflict" in call.reason.lower() for call in splice_calls):
        return True
    splice_directions = {
        call.direction
        for call in splice_calls
        if call.direction in {PredictionDirection.PATHOGENIC, PredictionDirection.BENIGN}
    }
    non_splice_directions = {
        call.direction
        for call in calls
        if not call.splice_related
        and call.direction in {PredictionDirection.PATHOGENIC, PredictionDirection.BENIGN}
    }
    return (
        len(splice_directions) > 1
        or (
            PredictionDirection.PATHOGENIC in splice_directions
            and PredictionDirection.BENIGN in non_splice_directions
        )
        or (
            PredictionDirection.BENIGN in splice_directions
            and PredictionDirection.PATHOGENIC in non_splice_directions
        )
    )


def _pp3_reason(calls: list[PredictorCall]) -> str:
    if any(call.splice_related for call in calls):
        return (
            "Multiple computational methods support a deleterious effect; SpliceAI contributes "
            "splice-related supporting evidence only and does not replace PVS1 or PS3."
        )
    return "Multiple computational methods support a deleterious effect."


def _evidence_item(
    *,
    variant: Variant,
    code: EvidenceCode,
    direction: EvidenceDirection,
    reason: str,
    calls: list[PredictorCall],
    all_calls: list[PredictorCall],
    predictions: list[ComputationalPrediction],
) -> EvidenceItem:
    timestamp = datetime.now(timezone.utc).isoformat()
    evidence_id = f"ev_comp_{variant.variant_id}_{code.value.lower()}"
    return EvidenceItem(
        evidence_id=evidence_id,
        code=code,
        strength=EvidenceStrength.SUPPORTING,
        direction=direction,
        reason=reason,
        source=EvidenceSource(
            name="ComputationalPredictionEvaluator",
            version="0.1.0",
            retrieval_timestamp=timestamp,
            query={"variant_id": variant.variant_id, "methods": [p.method for p in predictions]},
        ),
        confidence=_confidence(calls, all_calls),
        requires_review=True,
        triggered_by=[call.method for call in calls],
        supporting_data={
            "applied_strength": EvidenceStrength.SUPPORTING.value,
            "predictor_calls": [_call_data(call) for call in all_calls],
            "limitations": [
                "PP3/BP4 are applied only at supporting strength.",
                "Computational evidence does not replace functional evidence such as PS3.",
                "SpliceAI splice-related support does not replace PVS1.",
            ],
        },
        audit_trail=[
            AuditTrail(
                event_id=f"audit_{evidence_id}",
                event_type="computational_evidence_evaluated",
                tool_name="evaluate_computational_evidence",
                query={"variant_id": variant.variant_id},
                notes=[reason],
            )
        ],
    )


def _confidence(calls: list[PredictorCall], all_calls: list[PredictorCall]) -> float:
    if not all_calls:
        return 0.0
    return min(0.95, round(0.5 + 0.1 * len(calls), 2))


def _call_data(call: PredictorCall) -> dict[str, Any]:
    return {
        "method": call.method,
        "direction": call.direction.value,
        "score": call.score,
        "reason": call.reason,
        "transcript": call.transcript,
        "splice_related": call.splice_related,
    }


def _summary(
    calls: list[PredictorCall],
    thresholds: ComputationalEvidenceThresholds,
) -> dict[str, Any]:
    pathogenic = [call for call in calls if call.direction == PredictionDirection.PATHOGENIC]
    benign = [call for call in calls if call.direction == PredictionDirection.BENIGN]
    neutral = [call for call in calls if call.direction == PredictionDirection.NEUTRAL]
    return {
        "pathogenic_support_count": len({call.method for call in pathogenic}),
        "benign_support_count": len({call.method for call in benign}),
        "neutral_count": len(neutral),
        "thresholds": thresholds.model_dump(),
        "predictor_calls": [_call_data(call) for call in calls],
    }
