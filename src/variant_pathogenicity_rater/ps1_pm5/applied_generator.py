from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from variant_pathogenicity_rater.ps1_pm5.decision_tree import evaluate_ps1_pm5_decisions
from variant_pathogenicity_rater.ps1_pm5.schema import PS1PM5Decision
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import (
    ClinVarRecord,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.transcript_support.schema import TranscriptValidationResult


def generate_ps1_pm5_evidence(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    clinvar_records: list[ClinVarRecord],
    context_consistency: ContextConsistency | None = None,
    transcript_validation: TranscriptValidationResult | None = None,
    provider_provenance: dict[str, Any] | None = None,
) -> tuple[list[EvidenceItem], list[PS1PM5Decision]]:
    decisions = evaluate_ps1_pm5_decisions(
        variant=variant,
        context=context,
        clinvar_records=clinvar_records,
        context_consistency=context_consistency,
        transcript_validation=transcript_validation,
        provenance=provider_provenance,
    )
    items = [_decision_to_evidence_item(variant, decision) for decision in decisions]
    return [item for item in items if item is not None], decisions


def _decision_to_evidence_item(
    variant: Variant,
    decision: PS1PM5Decision,
) -> EvidenceItem | None:
    if decision.recommended_code not in {"PS1", "PM5"}:
        return None
    if decision.generation.status == "blocked" and _hard_block_without_review_note(decision):
        return None
    if decision.generation.status not in {"applied", "candidate", "blocked"}:
        return None

    code = EvidenceCode.PS1 if decision.recommended_code == "PS1" else EvidenceCode.PM5
    status = "applied" if decision.applied else "candidate"
    digest = sha1(
        (
            f"{variant.variant_id}:{decision.recommended_code}:"
            f"{decision.clinvar_comparison.variation_id}:{status}"
        ).encode()
    ).hexdigest()[:12]
    reason = decision.generation.criterion_rationale
    if not decision.applied and not reason.startswith("Candidate-only"):
        reason = f"Candidate-only ClinVar-derived {decision.recommended_code}: {reason}"

    return EvidenceItem(
        evidence_id=f"ev-ps1pm5-{digest}",
        code=code,
        strength=decision.strength if decision.applied else EvidenceStrength.NONE,
        direction=decision.direction if decision.applied else EvidenceDirection.PATHOGENIC,
        reason=reason,
        source=EvidenceSource(
            name="ClinVar",
            version=decision.clinvar_comparison.source_version,
            database_id=decision.clinvar_comparison.variation_id,
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query={
                "variant_id": variant.variant_id,
                "criterion": decision.recommended_code,
                "comparator_variation_id": decision.clinvar_comparison.variation_id,
            },
            raw_snapshot_ref=decision.clinvar_comparison.raw_snapshot_ref,
            provenance=decision.provenance,
        ),
        confidence=_confidence(decision),
        requires_review=True,
        candidate_only=not decision.applied,
        applied=decision.applied,
        triggered_by=["clinvar_comparator", "protein_change_comparison"],
        supporting_data={
            "ps1_pm5_decision": decision.model_dump(mode="json"),
            "amino_acid_match": decision.amino_acid_match.model_dump(mode="json"),
            "clinvar_comparison": decision.clinvar_comparison.model_dump(mode="json"),
            "condition_match": decision.condition_match.model_dump(mode="json"),
            "evidence_generation": decision.generation.model_dump(mode="json"),
            "decision_path": decision.generation.decision_path,
            "quality_checks": decision.quality_checks,
            "blocking_reasons": decision.blocking_reasons,
            "downgrade_reasons": decision.downgrade_reasons,
            "limitations": decision.limitations,
            "review_note": decision.generation.review_note,
            "not_pp5": True,
            "evidence_status": status,
            "candidate_only": not decision.applied,
            "applied": decision.applied,
        },
        audit_trail=[
            AuditTrail(
                event_id=f"audit-ps1pm5-{digest}",
                event_type="ps1_pm5_evidence_evaluated",
                tool_name="generate_ps1_pm5_evidence",
                query={"variant_id": variant.variant_id},
                notes=[decision.generation.criterion_rationale],
            )
        ],
        review_flags=_review_flags(decision),
    )


def _hard_block_without_review_note(decision: PS1PM5Decision) -> bool:
    hard_blocks = [
        "Condition mismatch",
        "same nucleotide/genomic variant",
        "not a different missense",
    ]
    return any(
        any(fragment in reason for fragment in hard_blocks)
        for reason in decision.blocking_reasons
    )


def _confidence(decision: PS1PM5Decision) -> float:
    if decision.applied:
        return 0.75 if decision.recommended_code == "PS1" else 0.7
    if decision.clinvar_comparison.has_conflict:
        return 0.25
    if decision.clinvar_comparison.low_quality_candidate_only:
        return 0.35
    return 0.4


def _review_flags(decision: PS1PM5Decision) -> list[ReviewFlag]:
    flags = [
        ReviewFlag(
            code="PS1_PM5_REQUIRES_REVIEW",
            message=(
                "ClinVar-derived PS1/PM5 evidence requires qualified human review "
                "and is not PP5."
            ),
            severity="warning",
            blocking=False,
        )
    ]
    if decision.clinvar_comparison.has_conflict:
        flags.append(
            ReviewFlag(
                code="PS1_PM5_CLINVAR_CONFLICT",
                message="ClinVar conflict prevents applied PS1/PM5.",
                severity="warning",
                blocking=True,
            )
        )
    if decision.condition_match.blocking:
        flags.append(
            ReviewFlag(
                code="PS1_PM5_CONDITION_MISMATCH",
                message="Condition mismatch or missing disease context prevents applied PS1/PM5.",
                severity="warning",
                blocking=True,
            )
        )
    return flags
