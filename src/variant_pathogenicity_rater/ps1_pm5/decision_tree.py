from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.ps1_pm5.clinvar_quality import compare_clinvar_record
from variant_pathogenicity_rater.ps1_pm5.condition import evaluate_condition_match
from variant_pathogenicity_rater.ps1_pm5.protein import compare_amino_acid_change
from variant_pathogenicity_rater.ps1_pm5.schema import (
    ClinVarComparison,
    PS1PM5Decision,
    PS1PM5EvidenceGeneration,
)
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import (
    ClinVarRecord,
    EvidenceDirection,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.transcript_support.schema import TranscriptValidationResult


REVIEW_NOTE = (
    "ClinVar-derived PS1/PM5 is a comparator-based machine proposal; it requires "
    "qualified human review and is not PP5 evidence."
)


def evaluate_ps1_pm5_decisions(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    clinvar_records: list[ClinVarRecord],
    context_consistency: ContextConsistency | None = None,
    transcript_validation: TranscriptValidationResult | None = None,
    provenance: dict[str, Any] | None = None,
) -> list[PS1PM5Decision]:
    return [
        evaluate_ps1_pm5_decision(
            variant=variant,
            context=context,
            record=record,
            source_record_count=len(clinvar_records),
            all_comparators_summary=[
                {
                    "variation_id": item.variation_id,
                    "clinical_significance": item.clinical_significance,
                    "review_status": item.review_status,
                }
                for item in clinvar_records
            ],
            context_consistency=context_consistency,
            transcript_validation=transcript_validation,
            provenance=provenance,
        )
        for record in clinvar_records
    ]


def evaluate_ps1_pm5_decision(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    record: ClinVarRecord,
    source_record_count: int = 1,
    all_comparators_summary: list[dict[str, Any]] | None = None,
    context_consistency: ContextConsistency | None = None,
    transcript_validation: TranscriptValidationResult | None = None,
    provenance: dict[str, Any] | None = None,
) -> PS1PM5Decision:
    amino = compare_amino_acid_change(variant, record)
    clinvar = compare_clinvar_record(variant, record)
    condition = evaluate_condition_match(context, record)
    checks = _quality_checks(amino, clinvar, condition, context_consistency, transcript_validation)
    blocking = [
        check["reason"]
        for check in checks
        if check.get("blocking") and not check["passed"]
    ]
    downgrades = [
        check["reason"] for check in checks if not check.get("blocking") and not check["passed"]
    ]
    decision_path: list[str] = []
    recommended_code: str | None = None
    strength = EvidenceStrength.NONE
    direction = EvidenceDirection.NEUTRAL
    applied = False
    candidate_only = False
    status = "unavailable"
    rationale = "No PS1/PM5-relevant ClinVar comparator was identified."

    if not clinvar.is_pathogenic_or_likely_pathogenic and not clinvar.has_conflict:
        decision_path.append("clinvar_not_pathogenic_unavailable")
        rationale = "ClinVar comparator is not P/LP; PS1/PM5 is unavailable."
    elif clinvar.same_nucleotide_change:
        status = "blocked"
        blocking.append(
            "Comparator is the same nucleotide/genomic variant; PS1/PM5 is not applicable."
        )
        rationale = "PS1/PM5 blocked because the comparator appears to be the same variant."
        decision_path.append("same_nucleotide_variant_blocked")
    elif not amino.protein_parseable:
        recommended_code = "PS1"
        candidate_only = True
        status = "candidate"
        rationale = "Protein consequence is missing or unparseable; PS1/PM5 remains candidate-only."
        decision_path.append("protein_unavailable_candidate_only")
    elif amino.same_amino_acid_change:
        recommended_code = "PS1"
        direction = EvidenceDirection.PATHOGENIC
        decision_path.append("same_amino_acid_change")
        if not clinvar.different_nucleotide_change:
            candidate_only = True
            status = "candidate"
            downgrades.append("Different nucleotide change could not be confirmed for PS1.")
            rationale = "PS1 remains candidate-only because nucleotide difference is unresolved."
        elif blocking:
            if _candidate_only_transcript_block(blocking):
                candidate_only = True
                status = "candidate"
                rationale = "PS1 remains candidate-only because transcript/protein metadata requires review."
            else:
                status = "blocked"
                rationale = "PS1 blocked by required safety gates."
        elif downgrades:
            candidate_only = True
            status = "candidate"
            rationale = "PS1 remains candidate-only because confidence gates were insufficient."
        else:
            applied = True
            strength = EvidenceStrength.STRONG
            status = "applied"
            rationale = (
                "PS1 applied: same amino acid change from a different nucleotide "
                "change with matched context."
            )
    elif amino.different_missense_change:
        recommended_code = "PM5"
        direction = EvidenceDirection.PATHOGENIC
        decision_path.append("same_residue_different_missense")
        if blocking:
            if _candidate_only_transcript_block(blocking):
                candidate_only = True
                status = "candidate"
                rationale = "PM5 remains candidate-only because transcript/protein metadata requires review."
            else:
                status = "blocked"
                rationale = "PM5 blocked by required safety gates."
        elif downgrades:
            candidate_only = True
            status = "candidate"
            rationale = "PM5 remains candidate-only because confidence gates were insufficient."
        else:
            applied = True
            strength = EvidenceStrength.MODERATE
            status = "applied"
            rationale = (
                "PM5 applied: different pathogenic missense change at the same "
                "residue with matched context."
            )
    elif amino.same_residue:
        status = "blocked"
        blocking.append("Same residue comparator is not a different missense change.")
        rationale = "PM5 blocked because the comparator is not a different missense change."

    if recommended_code and not applied:
        strength = EvidenceStrength.NONE
        candidate_only = status == "candidate"
    limitations = [
        *amino.limitations,
        *condition.limitations,
        *downgrades,
        *blocking,
    ]
    generation = PS1PM5EvidenceGeneration(
        status=status,
        candidate_only=not applied,
        automatic_application=False,
        criterion_rationale=rationale,
        review_note=REVIEW_NOTE,
        decision_path=decision_path,
        source_record_count=source_record_count,
        selected_comparator_variation_id=record.variation_id,
        all_comparators_summary=all_comparators_summary or [],
    )
    return PS1PM5Decision(
        recommended_code=recommended_code,  # type: ignore[arg-type]
        strength=strength,
        direction=direction,
        applied=applied,
        candidate_only=candidate_only,
        amino_acid_match=amino,
        clinvar_comparison=clinvar,
        condition_match=condition,
        generation=generation,
        quality_checks=checks,
        blocking_reasons=list(dict.fromkeys(blocking)),
        downgrade_reasons=list(dict.fromkeys(downgrades)),
        limitations=list(dict.fromkeys(limitations)),
        provenance={
            **(provenance or {}),
            "clinvar_source": record.source.model_dump(mode="json"),
            "context_consistency": (
                context_consistency.model_dump(mode="json")
                if context_consistency is not None
                else None
            ),
            "transcript_validation": (
                transcript_validation.model_dump(mode="json")
                if transcript_validation is not None
                else None
            ),
        },
    )


def _quality_checks(
    amino: Any,
    clinvar: ClinVarComparison,
    condition: Any,
    context_consistency: ContextConsistency | None,
    transcript_validation: TranscriptValidationResult | None,
) -> list[dict[str, Any]]:
    checks = [
        _check(
            "clinvar_pathogenic_or_likely_pathogenic",
            clinvar.is_pathogenic_or_likely_pathogenic,
            "ClinVar comparator is not pathogenic/likely pathogenic.",
        ),
        _check("clinvar_no_conflict", not clinvar.has_conflict, "ClinVar conflict blocks PS1/PM5."),
        _check(
            "clinvar_germline_applicable",
            clinvar.is_germline_applicable,
            "ClinVar comparator is not clearly germline applicable.",
        ),
        _check(
            "condition_match",
            condition.matched and not condition.blocking,
            "Condition mismatch or missing condition blocks applied PS1/PM5.",
        ),
        _check(
            "transcript_or_protein_match",
            amino.transcript_or_protein_match,
            "Transcript/protein mismatch blocks applied PS1/PM5.",
        ),
        _check(
            "clinvar_quality",
            clinvar.high_quality_for_applied,
            "ClinVar assertion quality is insufficient for applied PS1/PM5.",
            blocking=False,
        ),
    ]
    if context_consistency is not None and context_consistency.conflicts:
        checks.append(
            _check(
                "context_consistency",
                False,
                "Context consistency conflicts block applied PS1/PM5.",
            )
        )
    if transcript_validation is not None and transcript_validation.protein_accession_match is False:
        checks.append(
            _check(
                "transcript_validation_protein_accession",
                False,
                "Transcript metadata protein accession mismatch blocks applied PS1/PM5.",
            )
        )
    if transcript_validation is not None and transcript_validation.status == "conflict":
        checks.append(
            _check(
                "transcript_validation",
                False,
                "Transcript metadata validation conflict blocks applied PS1/PM5.",
            )
        )
    return checks


def _candidate_only_transcript_block(blocking: list[str]) -> bool:
    if not blocking:
        return False
    transcript_blocks = (
        "Transcript metadata protein accession mismatch",
        "Transcript metadata validation conflict",
        "Transcript/protein mismatch blocks applied PS1/PM5.",
    )
    return all(any(fragment in reason for fragment in transcript_blocks) for reason in blocking)


def _check(name: str, passed: bool, reason: str, *, blocking: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "reason": "passed" if passed else reason,
        "blocking": blocking,
    }
