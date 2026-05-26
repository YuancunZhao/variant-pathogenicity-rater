from __future__ import annotations

from variant_pathogenicity_rater.computational.schema import ComputationalEvidenceDecision
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem


def computational_safety_limitations() -> list[str]:
    return [
        "PP3/BP4 are applied only at supporting strength.",
        "Computational prediction is not functional evidence and cannot trigger PS3 or BS3.",
        "Computational splice prediction is not RNA validation.",
        "SpliceAI cannot trigger PVS1 and does not override the PVS1 engine.",
        "No single predictor can apply PP3 or BP4 by itself.",
    ]


def applied_pvs1_same_mechanism(existing_items: list[EvidenceItem]) -> bool:
    for item in existing_items:
        if str(item.code) != "PVS1":
            continue
        if item.candidate_only or item.applied is False or str(item.strength) == "none":
            continue
        return True
    return False


def enforce_pp3_bp4_exclusivity(decision: ComputationalEvidenceDecision) -> ComputationalEvidenceDecision:
    if decision.recommended_code not in {"PP3", "BP4"}:
        decision.applied = False
    if decision.strength != "supporting" and decision.applied:
        decision.strength = "supporting"  # type: ignore[assignment]
    decision.requires_review = True
    return decision

