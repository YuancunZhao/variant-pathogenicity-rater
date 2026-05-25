from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from variant_pathogenicity_rater.pvs1.decision_tree import run_pvs1_decision_tree
from variant_pathogenicity_rater.pvs1.schema import PVS1Config, PVS1Decision
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import EvidenceDirection, EvidenceItem, EvidenceSource, EvidenceStrength
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


STRENGTH_MAP = {
    "PVS1": EvidenceStrength.VERY_STRONG,
    "PVS1_Strong": EvidenceStrength.STRONG,
    "PVS1_Moderate": EvidenceStrength.MODERATE,
    "PVS1_Supporting": EvidenceStrength.SUPPORTING,
    "PVS1_candidate": EvidenceStrength.NONE,
    "not_applicable": EvidenceStrength.NONE,
}


def generate_pvs1_evidence(
    variant: Variant,
    *,
    annotation: VariantAnnotation | None = None,
    transcript_selection: TranscriptSelection | None = None,
    gene_disease_context: GeneDiseaseContext | None = None,
    context_consistency: ContextConsistency | None = None,
    provider_data: dict[str, Any] | None = None,
    manual_overrides: dict[str, Any] | None = None,
    config: PVS1Config | dict[str, Any] | None = None,
) -> tuple[EvidenceItem | None, PVS1Decision]:
    cfg = PVS1Config.model_validate(config or {}) if isinstance(config, dict) else (config or PVS1Config())
    context = gene_disease_context or GeneDiseaseContext(gene=variant.gene_symbol or "unknown", disease="not provided")
    decision = run_pvs1_decision_tree(
        variant,
        annotation=annotation,
        transcript_selection=transcript_selection,
        gene_disease_context=context,
        context_consistency=context_consistency,
        provider_data=provider_data,
        manual_overrides=manual_overrides,
        config=cfg,
    )
    if decision.strength == "not_applicable" and not decision.consequence:
        return None, decision
    if decision.recommended_code == "not_applicable" and not (decision.consequence and decision.consequence.is_lof):
        return None, decision

    item = EvidenceItem(
        evidence_id=_evidence_id(variant, decision),
        code=EvidenceCode.PVS1,
        strength=STRENGTH_MAP[decision.strength],
        direction=EvidenceDirection.PATHOGENIC,
        reason=_rationale(decision),
        source=EvidenceSource(
            name="PVS1DecisionTree",
            version="0.2.0",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query={
                "variant_id": variant.variant_id,
                "gene": context.gene_symbol,
                "disease": context.disease_name,
                "transcript": decision.transcript_relevance.transcript if decision.transcript_relevance else None,
            },
            provenance=decision.provenance,
        ),
        confidence=_confidence(decision),
        requires_review=True,
        applied=decision.applied,
        candidate_only=decision.candidate_only,
        triggered_by=["PVS1DecisionTree", "variant_consequence", "gene_disease_context", "transcript_relevance", "nmd_or_splice_path"],
        supporting_data={
            "requires_manual_review": True,
            "applied": decision.applied,
            "candidate_only": decision.candidate_only,
            "evidence_status": "applied" if decision.applied else "candidate",
            "applied_pvs1_level": decision.strength if decision.applied else None,
            "candidate_pvs1_level": decision.strength if decision.candidate_only else None,
            "pvs1_decision": decision.model_dump(mode="json"),
            "decision_path": decision.decision_path,
            "downgrade_reasons": decision.downgrade_reasons,
            "blocking_reasons": decision.blocking_reasons,
            "limitations": decision.limitations,
        },
        review_flags=_with_manual_review_flag(decision.review_flags, candidate_only=decision.candidate_only),
        audit_trail=[
            AuditTrail(
                event_id=f"audit-{_evidence_id(variant, decision)}",
                event_type="pvs1_decision_tree_evaluated",
                tool_name="generate_pvs1_evidence",
                query={"variant_id": variant.variant_id},
                notes=[*decision.decision_path, *decision.downgrade_reasons, *decision.blocking_reasons],
            )
        ],
    )
    return item, decision


def _rationale(decision: PVS1Decision) -> str:
    status = "applied" if decision.applied else "candidate-only"
    reasons = decision.downgrade_reasons or decision.blocking_reasons
    suffix = f" Reasons: {'; '.join(reasons)}" if reasons else ""
    return f"{decision.recommended_code} {status} by conservative ClinGen SVI-style PVS1 decision tree.{suffix}"


def _confidence(decision: PVS1Decision) -> float:
    base = {
        "PVS1": 0.86,
        "PVS1_Strong": 0.78,
        "PVS1_Moderate": 0.66,
        "PVS1_Supporting": 0.55,
        "PVS1_candidate": 0.3,
        "not_applicable": 0.0,
    }[decision.strength]
    base -= 0.05 * len(decision.downgrade_reasons)
    base -= 0.08 * len(decision.blocking_reasons)
    return round(max(0.0, min(1.0, base)), 2)


def _evidence_id(variant: Variant, decision: PVS1Decision) -> str:
    material = f"{variant.variant_id}:PVS1DecisionTree"
    return f"ev-pvs1dt-{sha1(material.encode()).hexdigest()[:12]}"


def _with_manual_review_flag(flags: list[ReviewFlag], *, candidate_only: bool) -> list[ReviewFlag]:
    output = list(flags)
    if candidate_only and not any(flag.code == "PVS1_CANDIDATE_ONLY" for flag in output):
        output.append(
            ReviewFlag(
                code="PVS1_CANDIDATE_ONLY",
                message="PVS1 is candidate/review-note only unless the decision tree supports applied evidence.",
                severity="warning",
                blocking=True,
            )
        )
    if not any(flag.code == "PVS1_MANUAL_REVIEW_REQUIRED" for flag in output):
        output.append(ReviewFlag(
            code="PVS1_MANUAL_REVIEW_REQUIRED",
            message="All generated PVS1 evidence requires qualified manual review.",
            severity="warning",
            blocking=False,
        ))
    return output
