from __future__ import annotations

from variant_pathogenicity_rater.pvs1.schema import PVS1Decision


def enforce_pvs1_safety(decision: PVS1Decision) -> PVS1Decision:
    decision.review_flags = list(decision.review_flags)
    decision.limitations = list(dict.fromkeys([*decision.limitations, "All PVS1 evidence requires manual review."]))
    if decision.blocking_reasons:
        decision.applied = False
        decision.candidate_only = True
        if decision.strength != "not_applicable":
            decision.strength = "PVS1_candidate"
        decision.recommended_code = "PVS1_candidate" if decision.consequence and decision.consequence.is_lof else "not_applicable"
    if decision.applied and decision.candidate_only:
        decision.applied = False
    return decision
