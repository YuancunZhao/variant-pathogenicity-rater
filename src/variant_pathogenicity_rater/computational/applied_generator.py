from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.computational.decision_tree import evaluate_computational_evidence_decision
from variant_pathogenicity_rater.computational.schema import ComputationalEvidenceDecision
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import Variant


def generate_computational_evidence(
    *,
    variant: Variant,
    predictions: list[ComputationalPrediction],
    thresholds: ComputationalEvidenceThresholds | None = None,
    annotation: VariantAnnotation | None = None,
    context_consistency: ContextConsistency | None = None,
    existing_evidence_items: list[EvidenceItem] | None = None,
    provider_provenance: dict[str, Any] | None = None,
) -> tuple[list[EvidenceItem], ComputationalEvidenceDecision]:
    thresholds = thresholds or ComputationalEvidenceThresholds()
    decision = evaluate_computational_evidence_decision(
        variant=variant,
        predictions=predictions,
        thresholds=thresholds,
        annotation=annotation,
        context_consistency=context_consistency,
        existing_evidence_items=existing_evidence_items or [],
        provider_provenance=provider_provenance,
    )
    item = _decision_to_evidence_item(variant, decision)
    return ([item] if item else []), decision


def _decision_to_evidence_item(
    variant: Variant,
    decision: ComputationalEvidenceDecision,
) -> EvidenceItem | None:
    if not decision.recommended_code:
        return None
    if not decision.applied and not (decision.candidate_only or decision.conflict_reasons):
        return None

    code = EvidenceCode.PP3 if decision.recommended_code == "PP3" else EvidenceCode.BP4
    status = "applied" if decision.applied else "candidate"
    evidence_id = f"ev_comp_{variant.variant_id}_{code.value.lower()}_{status}"
    reason = _reason(decision)
    flags = [
        ReviewFlag(
            code="COMPUTATIONAL_EVIDENCE_REQUIRES_REVIEW",
            message="Computational PP3/BP4 evidence requires qualified human review.",
            severity="warning",
            blocking=False,
        )
    ]
    if decision.conflict_reasons:
        flags.append(
            ReviewFlag(
                code="COMPUTATIONAL_PREDICTOR_CONFLICT",
                message="Predictor conflict prevents applied PP3/BP4.",
                severity="warning",
                blocking=False,
            )
        )

    return EvidenceItem(
        evidence_id=evidence_id,
        code=code,
        strength=EvidenceStrength.SUPPORTING if decision.applied else EvidenceStrength.NONE,
        direction=decision.direction if decision.applied else (decision.direction or EvidenceDirection.CONFLICTING),
        reason=reason,
        source=EvidenceSource(
            name="ComputationalEvidenceGenerator",
            version="phase-3",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query={"variant_id": variant.variant_id, "recommended_code": decision.recommended_code},
            provenance=decision.provenance,
        ),
        confidence=_confidence(decision),
        requires_review=True,
        candidate_only=not decision.applied,
        applied=decision.applied,
        triggered_by=_triggered_by(decision),
        supporting_data={
            "computational_evidence_decision": decision.model_dump(mode="json"),
            "predictor_summary": decision.predictor_summary,
            "predictor_groups": decision.predictor_groups,
            "consensus_direction": decision.consensus_direction,
            "thresholds_used": decision.thresholds_used,
            "quality_checks": decision.quality_checks,
            "conflict_reasons": decision.conflict_reasons,
            "double_counting_warnings": decision.double_counting_warnings,
            "limitations": decision.limitations,
            "evidence_status": status,
            "candidate_only": not decision.applied,
            "applied": decision.applied,
        },
        audit_trail=[
            AuditTrail(
                event_id=f"audit_{evidence_id}",
                event_type="computational_evidence_evaluated",
                tool_name="generate_computational_evidence",
                query={"variant_id": variant.variant_id},
                notes=[reason],
            )
        ],
        review_flags=flags,
    )


def _reason(decision: ComputationalEvidenceDecision) -> str:
    if decision.applied:
        suffix = ""
        if any(str(call.get("method")).lower() == "spliceai" for call in decision.predictor_summary):
            suffix = " SpliceAI does not replace PVS1 or PS3 and is not RNA validation."
        return (
            f"{decision.recommended_code} Supporting is applied because multiple calibrated "
            f"computational predictors reached {decision.consensus_direction} consensus; "
            "computational prediction is not functional evidence or RNA validation."
            f"{suffix}"
        )
    if decision.conflict_reasons:
        return (
            f"{decision.recommended_code or 'Computational'} evidence remains candidate-only "
            "because predictor conflict prevents applied PP3/BP4."
        )
    return (
        f"{decision.recommended_code} remains candidate-only because computational consensus "
        "or quality gates were insufficient for applied evidence."
    )


def _triggered_by(decision: ComputationalEvidenceDecision) -> list[str]:
    return [
        str(call.get("method"))
        for call in decision.predictor_summary
        if call.get("direction") == decision.consensus_direction
    ]


def _confidence(decision: ComputationalEvidenceDecision) -> float:
    if decision.applied:
        support = 0
        for group in decision.predictor_groups.values():
            if isinstance(group, dict):
                support = max(support, int(group.get("support_count") or 0))
        return min(0.85, round(0.45 + 0.1 * support, 2))
    return 0.35 if decision.conflict_reasons else 0.4
