from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from variant_pathogenicity_rater.computational.calibration import call_to_summary
from variant_pathogenicity_rater.computational.schema import (
    PredictorCall,
    PredictorConsensus,
    PredictorDirection,
    PredictorGroup,
)


def evaluate_predictor_consensus(calls: Iterable[PredictorCall]) -> dict[PredictorGroup, PredictorConsensus]:
    grouped: dict[PredictorGroup, list[PredictorCall]] = defaultdict(list)
    for call in calls:
        grouped[call.group].append(call)
    return {group: _evaluate_group(group, group_calls) for group, group_calls in grouped.items()}


def evaluate_missense_predictor_consensus(calls: Iterable[PredictorCall]) -> PredictorConsensus:
    return _evaluate_group(PredictorGroup.MISSENSE, [call for call in calls if call.group == PredictorGroup.MISSENSE])


def evaluate_splice_predictor_consensus(calls: Iterable[PredictorCall]) -> PredictorConsensus:
    return _evaluate_group(PredictorGroup.SPLICE, [call for call in calls if call.group == PredictorGroup.SPLICE])


def _evaluate_group(group: PredictorGroup, calls: list[PredictorCall]) -> PredictorConsensus:
    unique = _unique_by_method(calls)
    countable = [call for call in unique if not call.candidate_only]
    pathogenic = [call for call in countable if call.direction == PredictorDirection.PATHOGENIC]
    benign = [call for call in countable if call.direction == PredictorDirection.BENIGN]
    neutral = [call for call in countable if call.direction == PredictorDirection.NEUTRAL]
    ambiguous = [call for call in unique if call.direction == PredictorDirection.AMBIGUOUS or call.candidate_only]

    conflict_reasons: list[str] = []
    limitations: list[str] = []
    review_flags: list[str] = []
    direction = PredictorDirection.NEUTRAL
    support_count = 0
    opposing_count = 0
    applied_eligible = False
    candidate_only = False

    if pathogenic and benign:
        direction = PredictorDirection.AMBIGUOUS
        support_count = max(len(pathogenic), len(benign))
        opposing_count = min(len(pathogenic), len(benign))
        conflict_reasons.append(
            "Predictors support both deleterious and benign/no-effect directions."
        )
        review_flags.append("COMPUTATIONAL_PREDICTOR_CONFLICT")
        candidate_only = True
    elif pathogenic or benign:
        winning = pathogenic or benign
        direction = PredictorDirection.PATHOGENIC if pathogenic else PredictorDirection.BENIGN
        support_count = len(winning)
        opposing_count = 0
        if support_count >= 2 and support_count > len(neutral) + len(ambiguous):
            applied_eligible = not any(call.candidate_only for call in winning)
        else:
            candidate_only = True
            limitations.append("Predictor count or majority agreement is insufficient for applied evidence.")
    elif ambiguous:
        direction = PredictorDirection.AMBIGUOUS
        limitations.append("Only ambiguous computational predictor calls were available.")
    else:
        limitations.append("No directional computational predictor calls were available.")

    if ambiguous:
        review_flags.append("COMPUTATIONAL_AMBIGUOUS_PREDICTOR")
    if any(call.candidate_only for call in unique):
        candidate_only = True
        limitations.append("At least one predictor record is candidate-only due to quality or provenance checks.")

    return PredictorConsensus(
        group=group,
        consensus_direction=direction,
        applied_eligible=applied_eligible and not conflict_reasons,
        candidate_only=candidate_only and not applied_eligible,
        support_count=support_count,
        opposing_count=opposing_count,
        neutral_count=len(neutral),
        ambiguous_count=len(ambiguous),
        available_predictor_count=len(unique),
        predictor_summary=[call_to_summary(call) for call in unique],
        conflict_reasons=conflict_reasons,
        limitations=list(dict.fromkeys(limitations)),
        review_flags=list(dict.fromkeys(review_flags)),
    )


def _unique_by_method(calls: list[PredictorCall]) -> list[PredictorCall]:
    selected: dict[str, PredictorCall] = {}
    rank = {
        PredictorDirection.PATHOGENIC: 3,
        PredictorDirection.BENIGN: 3,
        PredictorDirection.AMBIGUOUS: 2,
        PredictorDirection.NEUTRAL: 1,
    }
    for call in calls:
        existing = selected.get(call.method)
        if existing is None or rank[call.direction] > rank[existing.direction]:
            selected[call.method] = call
    return list(selected.values())
