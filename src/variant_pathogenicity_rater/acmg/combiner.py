from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

from variant_pathogenicity_rater.schemas import (
    ACMGClassification,
    AuditTrail,
    EvidenceCode,
    EvidenceDirection,
    EvidenceItem,
    EvidenceStrength,
    GeneDiseaseContext,
    ReviewFlag,
    Variant,
    VariantType,
)
from variant_pathogenicity_rater.schemas.classification import ClassificationResult


PHASE_ONE_VARIANT_TYPES = {
    VariantType.SNV.value,
    VariantType.SMALL_INSERTION.value,
    VariantType.SMALL_DELETION.value,
    VariantType.SMALL_DELINS.value,
}

COMPUTATIONAL_CODES = {EvidenceCode.PP3.value, EvidenceCode.BP4.value}

STRENGTH_RANK = {
    EvidenceStrength.NONE.value: 0,
    EvidenceStrength.SUPPORTING.value: 1,
    EvidenceStrength.MODERATE.value: 2,
    EvidenceStrength.STRONG.value: 3,
    EvidenceStrength.VERY_STRONG.value: 4,
    EvidenceStrength.STAND_ALONE.value: 5,
}

CANONICAL_STRENGTH = {
    EvidenceCode.PVS1.value: EvidenceStrength.VERY_STRONG.value,
    EvidenceCode.PS1.value: EvidenceStrength.STRONG.value,
    EvidenceCode.PS2.value: EvidenceStrength.STRONG.value,
    EvidenceCode.PS3.value: EvidenceStrength.STRONG.value,
    EvidenceCode.PS4.value: EvidenceStrength.STRONG.value,
    EvidenceCode.PM1.value: EvidenceStrength.MODERATE.value,
    EvidenceCode.PM2.value: EvidenceStrength.MODERATE.value,
    EvidenceCode.PM3.value: EvidenceStrength.MODERATE.value,
    EvidenceCode.PM4.value: EvidenceStrength.MODERATE.value,
    EvidenceCode.PM5.value: EvidenceStrength.MODERATE.value,
    EvidenceCode.PM6.value: EvidenceStrength.MODERATE.value,
    EvidenceCode.PP1.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.PP2.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.PP3.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.PP4.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.PP5.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BA1.value: EvidenceStrength.STAND_ALONE.value,
    EvidenceCode.BS1.value: EvidenceStrength.STRONG.value,
    EvidenceCode.BS2.value: EvidenceStrength.STRONG.value,
    EvidenceCode.BS3.value: EvidenceStrength.STRONG.value,
    EvidenceCode.BS4.value: EvidenceStrength.STRONG.value,
    EvidenceCode.BP1.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BP2.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BP3.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BP4.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BP5.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BP6.value: EvidenceStrength.SUPPORTING.value,
    EvidenceCode.BP7.value: EvidenceStrength.SUPPORTING.value,
}


@dataclass(frozen=True)
class CountedEvidence:
    item: EvidenceItem
    strength: str


@dataclass(frozen=True)
class RuleMatch:
    classification: ACMGClassification
    rule: str


def classify_acmg(
    evidence_items: Sequence[EvidenceItem] | Variant,
    variant: Variant | Sequence[EvidenceItem] | None = None,
    gene_disease_context: GeneDiseaseContext | Sequence[str] | None = None,
    limitations: Sequence[str] | None = None,
    audit_trail: Sequence[AuditTrail] | None = None,
) -> ClassificationResult:
    """Combine already-triggered ACMG evidence items into a five-tier proposal.

    The public API is ``classify_acmg(evidence_items, variant, context=None)``.
    A small compatibility shim accepts the earlier internal order
    ``classify_acmg(variant, evidence_items, limitations)`` so existing
    orchestration code can fail soft while callers migrate.
    """

    evidence_items, variant, gene_disease_context, limitations = _normalize_arguments(
        evidence_items,
        variant,
        gene_disease_context,
        limitations,
    )

    base_limitations = [
        "Phase 1 classification supports SNV and small indel variants only.",
        "This engine combines supplied ACMG evidence items; it does not trigger evidence.",
        "All machine-generated classifications require qualified human review.",
    ]
    result_limitations = _unique([*base_limitations, *limitations])
    review_flags = [_human_review_flag()]

    if _value(variant.variant_type) not in PHASE_ONE_VARIANT_TYPES:
        result_limitations.append("Variant type is outside the phase-1 SNV/small indel scope.")
        review_flags.append(
            ReviewFlag(
                code="UNSUPPORTED_VARIANT_TYPE",
                message="Only SNV and small indel classification is supported in phase 1.",
                severity="error",
                blocking=True,
            )
        )

    counted, count_limitations = _prepare_counted_evidence(evidence_items)
    result_limitations = _unique([*result_limitations, *count_limitations])

    pathogenic = [
        item
        for item in counted
        if _value(item.item.direction) == EvidenceDirection.PATHOGENIC.value
    ]
    benign = [
        item
        for item in counted
        if _value(item.item.direction) == EvidenceDirection.BENIGN.value
    ]

    pathogenic_match = _match_pathogenic(pathogenic)
    benign_match = _match_benign(benign)
    conflicting_evidence = _conflicting_evidence(pathogenic, benign)

    if pathogenic_match and benign_match:
        final_classification = ACMGClassification.UNCERTAIN_SIGNIFICANCE
        applied_rule = "conflicting_classification_thresholds"
        review_flags.append(
            ReviewFlag(
                code="CONFLICTING_PATHOGENIC_AND_BENIGN_EVIDENCE",
                message=(
                    "Both pathogenic and benign ACMG evidence combinations met a classification "
                    "threshold; manual adjudication is required."
                ),
                severity="error",
                blocking=True,
            )
        )
    elif conflicting_evidence:
        final_classification = ACMGClassification.UNCERTAIN_SIGNIFICANCE
        applied_rule = "opposing_evidence_vus_review"
        review_flags.append(
            ReviewFlag(
                code="OPPOSING_PATHOGENIC_AND_BENIGN_EVIDENCE",
                message=(
                    "Pathogenic and benign ACMG evidence are both present; the machine "
                    "proposal defaults to VUS pending human adjudication."
                ),
                severity="error",
                blocking=True,
            )
        )
    elif benign_match:
        final_classification = benign_match.classification
        applied_rule = benign_match.rule
    elif pathogenic_match:
        final_classification = pathogenic_match.classification
        applied_rule = pathogenic_match.rule
    else:
        final_classification = ACMGClassification.UNCERTAIN_SIGNIFICANCE
        applied_rule = "default_vus"

    if (
        conflicting_evidence
        and applied_rule not in {"conflicting_classification_thresholds", "opposing_evidence_vus_review"}
    ):
        review_flags.append(
            ReviewFlag(
                code="OPPOSING_EVIDENCE_PRESENT",
                message=(
                    "Pathogenic and benign evidence are both present, but only one side "
                    "met a classification threshold."
                ),
                severity="warning",
                blocking=False,
            )
        )

    if _has_computational_opposed_by_stronger_evidence(pathogenic, benign, final_classification):
        result_limitations.append(
            "PP3/BP4 computational supporting evidence was present but did not override "
            "stronger ACMG evidence."
        )

    pathogenic_summary = _evidence_summary(pathogenic)
    benign_summary = _evidence_summary(benign)
    confidence = _confidence(final_classification, applied_rule, pathogenic_match, benign_match)
    result_id = _result_id(variant, counted, applied_rule)
    report_text = (
        f"ACMG combiner result is {final_classification.value} by {applied_rule}; "
        "human review is required."
    )

    return ClassificationResult(
        result_id=result_id,
        variant=variant,
        final_classification=final_classification,
        evidence_items=list(evidence_items),
        applied_combination_rule=applied_rule,
        pathogenic_evidence_summary=pathogenic_summary,
        benign_evidence_summary=benign_summary,
        conflicting_evidence=conflicting_evidence,
        limitations=_unique(result_limitations),
        confidence=confidence,
        human_review_required=True,
        report_text=report_text,
        review_flags=review_flags,
        audit_trail=list(audit_trail or []),
    )


def _normalize_arguments(
    evidence_items: Sequence[EvidenceItem] | Variant,
    variant: Variant | Sequence[EvidenceItem] | None,
    gene_disease_context: GeneDiseaseContext | Sequence[str] | None,
    limitations: Sequence[str] | None,
) -> tuple[list[EvidenceItem], Variant, GeneDiseaseContext | None, list[str]]:
    if isinstance(evidence_items, Variant):
        if not isinstance(variant, Sequence):
            raise TypeError("Legacy classify_acmg order requires an evidence item sequence.")
        normalized_limitations = (
            list(gene_disease_context)
            if isinstance(gene_disease_context, Sequence)
            and not isinstance(gene_disease_context, GeneDiseaseContext)
            else []
        )
        return (
            list(variant),
            evidence_items,
            None,
            _unique([*normalized_limitations, *(limitations or [])]),
        )

    if not isinstance(variant, Variant):
        raise TypeError("classify_acmg requires a Variant as the second argument.")
    context = gene_disease_context if isinstance(gene_disease_context, GeneDiseaseContext) else None
    supplied_limitations = limitations
    if (
        supplied_limitations is None
        and isinstance(gene_disease_context, Sequence)
        and not isinstance(gene_disease_context, GeneDiseaseContext)
    ):
        supplied_limitations = gene_disease_context
    return list(evidence_items), variant, context, _unique(supplied_limitations or [])


def _prepare_counted_evidence(
    evidence_items: Sequence[EvidenceItem],
) -> tuple[list[CountedEvidence], list[str]]:
    by_code_direction: dict[tuple[str, str], CountedEvidence] = {}
    limitations: list[str] = []

    for item in evidence_items:
        code = _value(item.code)
        direction = _value(item.direction)
        raw_strength = _value(item.strength)

        if _is_candidate_only(item):
            limitations.append(
                f"{code} evidence {item.evidence_id} was not counted because it is candidate-only."
            )
            continue
        if direction not in {EvidenceDirection.PATHOGENIC.value, EvidenceDirection.BENIGN.value}:
            limitations.append(
                f"{code} evidence {item.evidence_id} was not counted because direction "
                f"is {direction}."
            )
            continue
        if raw_strength == EvidenceStrength.NONE.value:
            limitations.append(
                f"{code} evidence {item.evidence_id} was not counted because strength is none."
            )
            continue

        strength = _effective_strength(code, raw_strength, limitations)
        _record_strength_modification(code, raw_strength, strength, limitations)

        key = (direction, code)
        candidate = CountedEvidence(item=item, strength=strength)
        existing = by_code_direction.get(key)
        if existing is None:
            by_code_direction[key] = candidate
            continue

        limitations.append(f"Duplicate {code} {direction} evidence was collapsed to one count.")
        if STRENGTH_RANK[strength] > STRENGTH_RANK[existing.strength]:
            by_code_direction[key] = candidate

    return list(by_code_direction.values()), _unique(limitations)


def _effective_strength(code: str, strength: str, limitations: list[str]) -> str:
    if (
        code in COMPUTATIONAL_CODES
        and STRENGTH_RANK[strength] > STRENGTH_RANK[EvidenceStrength.SUPPORTING.value]
    ):
        limitations.append(
            f"{code} was capped at supporting strength to avoid overweighting "
            "computational evidence."
        )
        return EvidenceStrength.SUPPORTING.value
    return strength


def _record_strength_modification(
    code: str,
    raw_strength: str,
    effective_strength: str,
    limitations: list[str],
) -> None:
    canonical = CANONICAL_STRENGTH.get(code)
    if canonical is None or raw_strength == canonical:
        return
    if code in COMPUTATIONAL_CODES and effective_strength == EvidenceStrength.SUPPORTING.value:
        return
    limitations.append(
        f"{code} applied at {raw_strength} strength instead of canonical {canonical}."
    )


def _match_pathogenic(items: Sequence[CountedEvidence]) -> RuleMatch | None:
    counts = _counts(items)
    very_strong = counts[EvidenceStrength.VERY_STRONG.value]
    strong = counts[EvidenceStrength.STRONG.value]
    moderate = counts[EvidenceStrength.MODERATE.value]
    supporting = counts[EvidenceStrength.SUPPORTING.value]

    if very_strong >= 1 and strong >= 1:
        return RuleMatch(ACMGClassification.PATHOGENIC, "pathogenic: 1 very_strong + >=1 strong")
    if very_strong >= 1 and moderate >= 2:
        return RuleMatch(ACMGClassification.PATHOGENIC, "pathogenic: 1 very_strong + >=2 moderate")
    if very_strong >= 1 and moderate >= 1 and supporting >= 1:
        return RuleMatch(
            ACMGClassification.PATHOGENIC,
            "pathogenic: 1 very_strong + 1 moderate + >=1 supporting",
        )
    if very_strong >= 1 and supporting >= 2:
        return RuleMatch(
            ACMGClassification.PATHOGENIC,
            "pathogenic: 1 very_strong + >=2 supporting",
        )
    if strong >= 2:
        return RuleMatch(ACMGClassification.PATHOGENIC, "pathogenic: >=2 strong")
    if strong >= 1 and moderate >= 3:
        return RuleMatch(ACMGClassification.PATHOGENIC, "pathogenic: 1 strong + >=3 moderate")
    if strong >= 1 and moderate >= 2 and supporting >= 2:
        return RuleMatch(
            ACMGClassification.PATHOGENIC,
            "pathogenic: 1 strong + 2 moderate + >=2 supporting",
        )
    if strong >= 1 and moderate >= 1 and supporting >= 4:
        return RuleMatch(
            ACMGClassification.PATHOGENIC,
            "pathogenic: 1 strong + 1 moderate + >=4 supporting",
        )

    if very_strong >= 1 and moderate >= 1:
        return RuleMatch(
            ACMGClassification.LIKELY_PATHOGENIC,
            "likely_pathogenic: 1 very_strong + 1 moderate",
        )
    if strong >= 1 and 1 <= moderate <= 2:
        return RuleMatch(
            ACMGClassification.LIKELY_PATHOGENIC,
            "likely_pathogenic: 1 strong + 1-2 moderate",
        )
    if strong >= 1 and supporting >= 2:
        return RuleMatch(
            ACMGClassification.LIKELY_PATHOGENIC,
            "likely_pathogenic: 1 strong + >=2 supporting",
        )
    if moderate >= 3:
        return RuleMatch(ACMGClassification.LIKELY_PATHOGENIC, "likely_pathogenic: >=3 moderate")
    if moderate >= 2 and supporting >= 2:
        return RuleMatch(
            ACMGClassification.LIKELY_PATHOGENIC,
            "likely_pathogenic: 2 moderate + >=2 supporting",
        )
    if moderate >= 1 and supporting >= 4:
        return RuleMatch(
            ACMGClassification.LIKELY_PATHOGENIC,
            "likely_pathogenic: 1 moderate + >=4 supporting",
        )

    return None


def _match_benign(items: Sequence[CountedEvidence]) -> RuleMatch | None:
    counts = _counts(items)
    stand_alone_codes = {
        _value(item.item.code)
        for item in items
        if item.strength == EvidenceStrength.STAND_ALONE.value
    }
    strong = counts[EvidenceStrength.STRONG.value]
    supporting = counts[EvidenceStrength.SUPPORTING.value]

    if EvidenceCode.BA1.value in stand_alone_codes:
        return RuleMatch(ACMGClassification.BENIGN, "benign: BA1 stand_alone")
    if strong >= 2:
        return RuleMatch(ACMGClassification.BENIGN, "benign: >=2 strong")
    if strong >= 1 and supporting >= 1:
        return RuleMatch(
            ACMGClassification.LIKELY_BENIGN,
            "likely_benign: 1 strong + >=1 supporting",
        )
    if supporting >= 2:
        return RuleMatch(ACMGClassification.LIKELY_BENIGN, "likely_benign: >=2 supporting")

    return None


def _counts(items: Sequence[CountedEvidence]) -> dict[str, int]:
    return {
        EvidenceStrength.STAND_ALONE.value: sum(
            1 for item in items if item.strength == EvidenceStrength.STAND_ALONE.value
        ),
        EvidenceStrength.VERY_STRONG.value: sum(
            1 for item in items if item.strength == EvidenceStrength.VERY_STRONG.value
        ),
        EvidenceStrength.STRONG.value: sum(
            1 for item in items if item.strength == EvidenceStrength.STRONG.value
        ),
        EvidenceStrength.MODERATE.value: sum(
            1 for item in items if item.strength == EvidenceStrength.MODERATE.value
        ),
        EvidenceStrength.SUPPORTING.value: sum(
            1 for item in items if item.strength == EvidenceStrength.SUPPORTING.value
        ),
    }


def _evidence_summary(items: Sequence[CountedEvidence]) -> list[str]:
    return sorted(
        f"{_value(item.item.code)} {item.strength}: {item.item.reason}"
        for item in items
    )


def _conflicting_evidence(
    pathogenic: Sequence[CountedEvidence],
    benign: Sequence[CountedEvidence],
) -> list[str]:
    if not pathogenic or not benign:
        return []
    pathogenic_codes = ", ".join(sorted({_value(item.item.code) for item in pathogenic}))
    benign_codes = ", ".join(sorted({_value(item.item.code) for item in benign}))
    return [
        f"Pathogenic evidence ({pathogenic_codes}) and benign evidence ({benign_codes}) "
        "are both present."
    ]


def _has_computational_opposed_by_stronger_evidence(
    pathogenic: Sequence[CountedEvidence],
    benign: Sequence[CountedEvidence],
    final_classification: ACMGClassification,
) -> bool:
    pathogenic_computational = any(
        _value(item.item.code) == EvidenceCode.PP3.value for item in pathogenic
    )
    benign_computational = any(_value(item.item.code) == EvidenceCode.BP4.value for item in benign)
    if final_classification in {ACMGClassification.BENIGN, ACMGClassification.LIKELY_BENIGN}:
        return pathogenic_computational
    if final_classification in {
        ACMGClassification.PATHOGENIC,
        ACMGClassification.LIKELY_PATHOGENIC,
    }:
        return benign_computational
    return False


def _confidence(
    final_classification: ACMGClassification,
    applied_rule: str,
    pathogenic_match: RuleMatch | None,
    benign_match: RuleMatch | None,
) -> float:
    if applied_rule in {"conflicting_classification_thresholds", "opposing_evidence_vus_review"}:
        return 0.2
    if final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE:
        return 0.35
    if final_classification in {ACMGClassification.PATHOGENIC, ACMGClassification.BENIGN}:
        return 0.75
    if pathogenic_match or benign_match:
        return 0.55
    return 0.35


def _result_id(variant: Variant, counted: Sequence[CountedEvidence], applied_rule: str) -> str:
    evidence_key = "|".join(
        sorted(
            f"{_value(item.item.direction)}:{_value(item.item.code)}:{item.strength}"
            for item in counted
        )
    )
    digest = sha256(f"{variant.variant_id}|{applied_rule}|{evidence_key}".encode()).hexdigest()[:12]
    return f"acmg-classification-{digest}"


def _human_review_flag() -> ReviewFlag:
    return ReviewFlag(
        code="HUMAN_REVIEW_REQUIRED",
        message=(
            "All ACMG classifications are machine proposals and require qualified "
            "human review."
        ),
        severity="warning",
        blocking=True,
    )


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _value(value: object) -> str:
    return getattr(value, "value", value)


def _is_candidate_only(item: EvidenceItem) -> bool:
    return bool(
        item.supporting_data.get("candidate_only")
        or item.supporting_data.get("evidence_status") == "candidate"
        or item.supporting_data.get("applied") is False
    )
