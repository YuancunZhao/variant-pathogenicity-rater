from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.schemas.classification import ClassificationResult
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.vcep_profiles import vcep_report_payload


RunStep = Callable[[str, list[AuditTrail], list[str], Callable[[], Any]], Any | None]


@dataclass(frozen=True)
class ClassificationPhaseResult:
    classification_result: ClassificationResult


def run_classification_phase(
    *,
    evidence_items: list[EvidenceItem],
    normalized_variant: Variant,
    context: GeneDiseaseContext,
    limitations: list[str],
    audit_trail: list[AuditTrail],
    step_results: dict[str, Any],
    run_step: RunStep,
    transcript_selection: Any = None,
    transcript_validation: Any = None,
    variant_resolution: Any = None,
    context_consistency: ContextConsistency | None = None,
    provider_dependency_review_flags: list[ReviewFlag] | None = None,
    reviewed_review_flags: list[ReviewFlag] | None = None,
    clingen_erepo_result: Any = None,
    vcep_signal_result: Any = None,
    vcep_override_context: Any = None,
) -> ClassificationPhaseResult:
    classification_result = run_step(
        "classify_acmg",
        audit_trail,
        limitations,
        lambda: classify_acmg(evidence_items, normalized_variant, context, _unique(limitations)),
    )
    if classification_result is None:
        classification_result = classify_acmg([], normalized_variant, context, _unique(limitations))
    classification_result.transcript_selection = transcript_selection
    classification_result.transcript_validation = transcript_validation
    classification_result.variant_resolution = variant_resolution
    classification_result.context_consistency = context_consistency
    if transcript_selection is not None:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *transcript_selection.review_flags]
        )
    if context_consistency is not None:
        classification_result.review_flags = _unique_review_flags(
            [
                *classification_result.review_flags,
                *_review_flags_from_context_consistency(context_consistency),
            ]
        )
    if transcript_validation is not None:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *transcript_validation.review_flags]
        )
    if variant_resolution is not None:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *variant_resolution.review_flags]
        )
    if provider_dependency_review_flags:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *provider_dependency_review_flags]
        )
    if reviewed_review_flags:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *reviewed_review_flags]
        )
    if clingen_erepo_result is not None:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *clingen_erepo_result.review_flags]
        )
    if vcep_signal_result is not None:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *vcep_signal_result.review_flags]
        )
    if vcep_override_context is not None:
        classification_result.review_flags = _unique_review_flags(
            [
                *classification_result.review_flags,
                *vcep_override_context.review_required_flags,
            ]
        )
    classification_result.vcep_profile_context = vcep_report_payload(
        vcep_signal_result,
        vcep_override_context,
    )
    step_results["classify_acmg"] = json.loads(classification_result.model_dump_json())
    return ClassificationPhaseResult(classification_result=classification_result)


def _review_flags_from_context_consistency(consistency: ContextConsistency) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    for check in [*consistency.conflicts, *consistency.warnings]:
        flags.append(
            ReviewFlag(
                code=f"CONTEXT_{check.check_name.upper()}",
                message=check.reason,
                severity="error" if check.severity == "conflict" else "warning",
                blocking=check.severity in {"conflict", "insufficient"},
            )
        )
    return flags


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _unique_review_flags(flags: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for flag in flags:
        code = getattr(flag, "code", None)
        if not code or code in seen:
            continue
        seen.add(code)
        unique.append(flag)
    return unique
