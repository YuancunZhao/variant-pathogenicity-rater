from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.computational.calibration import call_to_summary, calibrate_prediction
from variant_pathogenicity_rater.computational.consensus import (
    evaluate_missense_predictor_consensus,
    evaluate_predictor_consensus,
    evaluate_splice_predictor_consensus,
)
from variant_pathogenicity_rater.computational.quality import computational_quality_checks
from variant_pathogenicity_rater.computational.safety import (
    applied_pvs1_same_mechanism,
    computational_safety_limitations,
    enforce_pp3_bp4_exclusivity,
)
from variant_pathogenicity_rater.computational.schema import (
    ComputationalEvidenceDecision,
    PredictorCall,
    PredictorConsensus,
    PredictorDirection,
    PredictorGroup,
)
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceDirection,
    EvidenceItem,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import Variant


def evaluate_computational_evidence_decision(
    *,
    variant: Variant,
    predictions: list[ComputationalPrediction],
    thresholds: ComputationalEvidenceThresholds,
    annotation: VariantAnnotation | None = None,
    context_consistency: ContextConsistency | None = None,
    existing_evidence_items: list[EvidenceItem] | None = None,
    provider_provenance: dict[str, Any] | None = None,
) -> ComputationalEvidenceDecision:
    calls = [calibrate_prediction(prediction, thresholds) for prediction in predictions]
    quality_checks = computational_quality_checks(
        variant=variant,
        calls=calls,
        annotation=annotation,
        context_consistency=context_consistency,
    )
    groups = evaluate_predictor_consensus(calls)
    missense = evaluate_missense_predictor_consensus(calls)
    splice = evaluate_splice_predictor_consensus(calls)
    overall = _overall_consensus(calls, thresholds)
    decision = _select_decision(
        calls=calls,
        missense=missense,
        splice=splice,
        overall=overall,
        quality_checks=quality_checks,
        thresholds=thresholds,
        provider_provenance=provider_provenance,
    )
    groups[PredictorGroup.META] = overall
    decision.predictor_groups = {
        getattr(group, "value", str(group)): consensus.model_dump(mode="json")
        for group, consensus in groups.items()
    }
    decision.predictor_summary = [call_to_summary(call) for call in calls]
    decision.provenance = {
        "providers": provider_provenance or {},
        "source_names": sorted({call.source_name for call in calls if call.source_name}),
        "source_versions": sorted({call.source_version for call in calls if call.source_version}),
    }
    decision.limitations = list(dict.fromkeys([*decision.limitations, *computational_safety_limitations()]))

    if applied_pvs1_same_mechanism(existing_evidence_items or []) and _splice_supports_pathogenic(calls):
        warning = "Applied PVS1 is already present for a possible splice/LoF mechanism; avoid double counting SpliceAI-based PP3."
        decision.double_counting_warnings.append(warning)
        if decision.applied and decision.recommended_code == "PP3":
            decision.applied = False
            decision.candidate_only = True
            decision.limitations.append(warning)

    return enforce_pp3_bp4_exclusivity(decision)


def _select_decision(
    *,
    calls: list[PredictorCall],
    missense: PredictorConsensus,
    splice: PredictorConsensus,
    overall: PredictorConsensus,
    quality_checks: list[dict[str, Any]],
    thresholds: ComputationalEvidenceThresholds,
    provider_provenance: dict[str, Any] | None,
) -> ComputationalEvidenceDecision:
    thresholds_used = thresholds.model_dump(mode="json")
    if not calls:
        return ComputationalEvidenceDecision(
            thresholds_used=thresholds_used,
            quality_checks=quality_checks,
            limitations=["No computational predictor data were supplied."],
            provenance=provider_provenance or {},
        )

    if all(call.candidate_only for call in calls):
        return ComputationalEvidenceDecision(
            thresholds_used=thresholds_used,
            quality_checks=quality_checks,
            limitations=[
                "All computational predictor records were candidate-only due to quality or provenance checks."
            ],
            provenance=provider_provenance or {},
        )

    conflict_reasons = [*missense.conflict_reasons, *splice.conflict_reasons, *overall.conflict_reasons]
    limitations = [*missense.limitations, *splice.limitations, *overall.limitations]
    if conflict_reasons:
        return ComputationalEvidenceDecision(
            recommended_code=_candidate_code(missense, splice, overall),
            strength=EvidenceStrength.NONE,
            direction=EvidenceDirection.CONFLICTING,
            applied=False,
            candidate_only=True,
            consensus_direction=PredictorDirection.AMBIGUOUS,
            thresholds_used=thresholds_used,
            quality_checks=quality_checks,
            conflict_reasons=conflict_reasons,
            limitations=limitations,
            provenance=provider_provenance or {},
        )

    preferred = _preferred_consensus(missense, splice, overall)
    if preferred is None or preferred.consensus_direction not in {PredictorDirection.PATHOGENIC, PredictorDirection.BENIGN}:
        return ComputationalEvidenceDecision(
            thresholds_used=thresholds_used,
            quality_checks=quality_checks,
            limitations=limitations or ["No calibrated consensus direction was available."],
            provenance=provider_provenance or {},
        )

    code = "PP3" if preferred.consensus_direction == PredictorDirection.PATHOGENIC else "BP4"
    direction = EvidenceDirection.PATHOGENIC if code == "PP3" else EvidenceDirection.BENIGN
    blockers = _application_blockers(code, preferred, quality_checks, thresholds)
    applied = not blockers and preferred.applied_eligible
    candidate_only = bool(blockers or preferred.candidate_only or not preferred.applied_eligible)
    return ComputationalEvidenceDecision(
        recommended_code=code,
        strength=EvidenceStrength.SUPPORTING if applied else EvidenceStrength.NONE,
        direction=direction,
        applied=applied,
        candidate_only=candidate_only,
        consensus_direction=preferred.consensus_direction,
        thresholds_used=thresholds_used,
        quality_checks=quality_checks,
        conflict_reasons=[],
        limitations=list(dict.fromkeys([*limitations, *blockers])),
        provenance=provider_provenance or {},
    )


def _preferred_consensus(
    missense: PredictorConsensus,
    splice: PredictorConsensus,
    overall: PredictorConsensus,
) -> PredictorConsensus | None:
    candidates = [
        consensus
        for consensus in (overall, missense, splice)
        if consensus.available_predictor_count and consensus.consensus_direction in {PredictorDirection.PATHOGENIC, PredictorDirection.BENIGN}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.applied_eligible, item.support_count, item.available_predictor_count))


def _application_blockers(
    code: str,
    consensus: PredictorConsensus,
    quality_checks: list[dict[str, Any]],
    thresholds: ComputationalEvidenceThresholds,
) -> list[str]:
    blockers: list[str] = []
    required = (
        thresholds.min_pathogenic_supporting_tools
        if code == "PP3"
        else thresholds.min_benign_supporting_tools
    )
    if consensus.support_count < required:
        blockers.append(
            f"At least {required} calibrated predictors are required for applied computational evidence."
        )
    if consensus.group == PredictorGroup.MISSENSE and not _passed(quality_checks, "missense_variant_type"):
        blockers.append("Missense computational predictors are not applicable to this variant consequence.")
    if consensus.group == PredictorGroup.SPLICE and not _passed(quality_checks, "splice_relevance"):
        blockers.append("Splice computational predictors are not applicable without splice-relevant context.")
    if consensus.group == PredictorGroup.SPLICE and code == "BP4":
        blockers.append("Low SpliceAI alone cannot apply BP4.")
    if consensus.group == PredictorGroup.META:
        groups = {
            str(call.get("group"))
            for call in consensus.predictor_summary
            if call.get("direction") == consensus.consensus_direction
        }
        if PredictorGroup.MISSENSE.value in groups and not _passed(quality_checks, "missense_variant_type"):
            blockers.append("Missense computational predictors are not applicable to this variant consequence.")
        if PredictorGroup.SPLICE.value in groups and not _passed(quality_checks, "splice_relevance"):
            blockers.append("Splice computational predictors are not applicable without splice-relevant context.")
        if code == "BP4" and consensus.support_count == 1 and PredictorGroup.SPLICE.value in groups:
            blockers.append("Low SpliceAI alone cannot apply BP4.")
    for check_name in ("context_consistency", "source_quality", "transcript_match", "genome_build_match"):
        if not _passed(quality_checks, check_name):
            blockers.append(f"Quality check failed: {check_name}.")
    return blockers


def _passed(checks: list[dict[str, Any]], name: str) -> bool:
    return any(check.get("name") == name and check.get("passed") for check in checks)


def _candidate_code(
    missense: PredictorConsensus,
    splice: PredictorConsensus,
    overall: PredictorConsensus,
) -> str | None:
    directions = {missense.consensus_direction, splice.consensus_direction, overall.consensus_direction}
    if PredictorDirection.PATHOGENIC in directions:
        return "PP3"
    if PredictorDirection.BENIGN in directions:
        return "BP4"
    return None


def _splice_supports_pathogenic(calls: list[PredictorCall]) -> bool:
    return any(call.group == PredictorGroup.SPLICE and call.direction == PredictorDirection.PATHOGENIC for call in calls)


def _overall_consensus(
    calls: list[PredictorCall],
    thresholds: ComputationalEvidenceThresholds,
) -> PredictorConsensus:
    unique = _unique_countable_calls(calls)
    pathogenic = [call for call in unique if call.direction == PredictorDirection.PATHOGENIC]
    benign = [call for call in unique if call.direction == PredictorDirection.BENIGN]
    neutral = [call for call in unique if call.direction == PredictorDirection.NEUTRAL]
    ambiguous = [call for call in unique if call.direction == PredictorDirection.AMBIGUOUS]
    limitations: list[str] = []
    conflict_reasons: list[str] = []
    review_flags: list[str] = []
    direction = PredictorDirection.NEUTRAL
    support_count = 0
    opposing_count = 0
    required = min(thresholds.min_pathogenic_supporting_tools, thresholds.min_benign_supporting_tools)

    if pathogenic and benign:
        direction = PredictorDirection.AMBIGUOUS
        support_count = max(len(pathogenic), len(benign))
        opposing_count = min(len(pathogenic), len(benign))
        conflict_reasons.append(
            "Across computational predictor groups, pathogenic and benign/no-effect calls conflict."
        )
        review_flags.append("COMPUTATIONAL_PREDICTOR_CONFLICT")
    elif pathogenic or benign:
        winning = pathogenic or benign
        direction = PredictorDirection.PATHOGENIC if pathogenic else PredictorDirection.BENIGN
        support_count = len(winning)
        required = (
            thresholds.min_pathogenic_supporting_tools
            if direction == PredictorDirection.PATHOGENIC
            else thresholds.min_benign_supporting_tools
        )
        if support_count < required or support_count <= len(neutral) + len(ambiguous):
            limitations.append(
                "Overall predictor count or majority agreement is insufficient for applied evidence."
            )
    elif ambiguous:
        direction = PredictorDirection.AMBIGUOUS
        limitations.append("Only ambiguous computational predictor calls were available.")
    else:
        limitations.append("No countable computational predictor calls were available.")

    return PredictorConsensus(
        group=PredictorGroup.META,
        consensus_direction=direction,
        applied_eligible=bool(
            support_count >= required
            and direction in {PredictorDirection.PATHOGENIC, PredictorDirection.BENIGN}
            and not conflict_reasons
        ),
        candidate_only=bool(
            direction in {PredictorDirection.PATHOGENIC, PredictorDirection.BENIGN}
            and (support_count < required or bool(limitations))
        ),
        support_count=support_count,
        opposing_count=opposing_count,
        neutral_count=len(neutral),
        ambiguous_count=len(ambiguous),
        available_predictor_count=len(unique),
        required_support_count=required,
        predictor_summary=[call_to_summary(call) for call in unique],
        conflict_reasons=conflict_reasons,
        limitations=limitations,
        review_flags=review_flags,
    )


def _unique_countable_calls(calls: list[PredictorCall]) -> list[PredictorCall]:
    selected: dict[str, PredictorCall] = {}
    rank = {
        PredictorDirection.PATHOGENIC: 3,
        PredictorDirection.BENIGN: 3,
        PredictorDirection.AMBIGUOUS: 2,
        PredictorDirection.NEUTRAL: 1,
    }
    for call in calls:
        if call.candidate_only:
            continue
        existing = selected.get(call.method)
        if existing is None or rank[call.direction] > rank[existing.direction]:
            selected[call.method] = call
    return list(selected.values())
