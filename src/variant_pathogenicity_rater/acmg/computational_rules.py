from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.computational import generate_computational_evidence
from variant_pathogenicity_rater.computational.schema import ComputationalEvidenceDecision
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import ComputationalPrediction, EvidenceItem
from variant_pathogenicity_rater.schemas.variant import Variant


def evaluate_computational_predictions(
    variant: Variant,
    predictions: list[ComputationalPrediction],
    thresholds: ComputationalEvidenceThresholds | None = None,
    *,
    annotation: VariantAnnotation | None = None,
    context_consistency: ContextConsistency | None = None,
    existing_evidence_items: list[EvidenceItem] | None = None,
    provider_provenance: dict[str, Any] | None = None,
) -> tuple[list[EvidenceItem], list[ReviewFlag], dict[str, Any]]:
    items, decision = generate_computational_evidence(
        variant=variant,
        predictions=predictions,
        thresholds=thresholds,
        annotation=annotation,
        context_consistency=context_consistency,
        existing_evidence_items=existing_evidence_items or [],
        provider_provenance=provider_provenance,
    )
    return items, _review_flags(decision), _summary(decision)


def _review_flags(decision: ComputationalEvidenceDecision) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    if _spliceai_prediction_conflict(decision):
        flags.append(
            ReviewFlag(
                code="SPLICEAI_PREDICTION_CONFLICT",
                message="SpliceAI score and predicted consequence conflict; PP3/BP4 were not applied.",
                severity="warning",
                blocking=False,
            )
        )
        return flags
    if decision.conflict_reasons:
        flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_CONFLICT",
                message="Computational predictors conflict; PP3/BP4 were not applied.",
                severity="warning",
                blocking=False,
            )
        )
    elif any(
        "candidate-only due to quality or provenance checks" in limitation
        for limitation in decision.limitations
    ):
        flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_INSUFFICIENT",
                message="Computational predictors did not meet consensus or quality gates for applied evidence.",
                severity="info",
                blocking=False,
            )
        )
    elif decision.recommended_code and decision.candidate_only:
        flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_INSUFFICIENT",
                message="Computational predictors did not meet consensus or quality gates for applied evidence.",
                severity="info",
                blocking=False,
            )
        )
    elif not decision.recommended_code and decision.predictor_summary:
        flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTION_AMBIGUOUS",
                message="Computational predictors were ambiguous or not applicable.",
                severity="info",
                blocking=False,
            )
        )
    return flags


def _spliceai_prediction_conflict(decision: ComputationalEvidenceDecision) -> bool:
    return any(
        str(call.get("method")).lower() == "spliceai"
        and "conflict" in str(call.get("reason", "")).lower()
        for call in decision.predictor_summary
    )


def _summary(decision: ComputationalEvidenceDecision) -> dict[str, Any]:
    pathogenic = [
        call for call in decision.predictor_summary if call.get("direction") == "pathogenic"
    ]
    benign = [call for call in decision.predictor_summary if call.get("direction") == "benign"]
    neutral = [call for call in decision.predictor_summary if call.get("direction") == "neutral"]
    return {
        "pathogenic_support_count": len({call.get("method") for call in pathogenic}),
        "benign_support_count": len({call.get("method") for call in benign}),
        "neutral_count": len(neutral),
        "thresholds": decision.thresholds_used,
        "predictor_calls": decision.predictor_summary,
        "decision": decision.model_dump(mode="json"),
        "consensus_direction": decision.consensus_direction,
        "conflict_reasons": decision.conflict_reasons,
    }
