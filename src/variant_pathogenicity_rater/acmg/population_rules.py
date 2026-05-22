from __future__ import annotations

from hashlib import sha1

from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import (
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    PopulationFrequency,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


def evaluate_population_rules(
    variant: Variant,
    gene_disease_context: GeneDiseaseContext,
    population_frequency: PopulationFrequency,
    thresholds: PopulationRuleThresholds | None = None,
) -> list[EvidenceItem]:
    thresholds = thresholds or PopulationRuleThresholds()
    review_flags = _review_flags(gene_disease_context, population_frequency, thresholds)
    confidence = _confidence(review_flags, gene_disease_context, thresholds)
    observed_af = _observed_af(population_frequency)
    candidate_only = any(flag.blocking for flag in review_flags)

    if observed_af is not None and observed_af >= thresholds.ba1_af_threshold:
        return [
            _item(
                variant=variant,
                code=EvidenceCode.BA1,
                strength=EvidenceStrength.STAND_ALONE,
                direction=EvidenceDirection.BENIGN,
                reason=(
                    "Population frequency meets or exceeds the configured BA1 threshold "
                    f"({observed_af:g} >= {thresholds.ba1_af_threshold:g})."
                ),
                population_frequency=population_frequency,
                confidence=confidence,
                review_flags=review_flags,
                thresholds=thresholds,
                candidate_only=candidate_only,
            )
        ]

    if observed_af is not None and observed_af >= thresholds.bs1_af_threshold:
        return [
            _item(
                variant=variant,
                code=EvidenceCode.BS1,
                strength=EvidenceStrength.STRONG,
                direction=EvidenceDirection.BENIGN,
                reason=(
                    "Population frequency meets or exceeds the configured BS1 threshold "
                    f"({observed_af:g} >= {thresholds.bs1_af_threshold:g})."
                ),
                population_frequency=population_frequency,
                confidence=confidence,
                review_flags=review_flags,
                thresholds=thresholds,
                candidate_only=candidate_only,
            )
        ]

    if observed_af is not None and _is_absent_or_extremely_rare(population_frequency, thresholds):
        return [
            _item(
                variant=variant,
                code=EvidenceCode.PM2,
                strength=EvidenceStrength.SUPPORTING,
                direction=EvidenceDirection.PATHOGENIC,
                reason=(
                    "Variant is absent from the configured population dataset or below the "
                    f"PM2 rarity threshold ({thresholds.pm2_af_threshold:g})."
                ),
                population_frequency=population_frequency,
                confidence=confidence,
                review_flags=review_flags,
                thresholds=thresholds,
                candidate_only=candidate_only,
            )
        ]

    return []


def _observed_af(population_frequency: PopulationFrequency) -> float | None:
    values = [
        value
        for value in [population_frequency.overall_af, population_frequency.max_pop_af]
        if value is not None
    ]
    if not values:
        return None
    return max(values)


def _is_absent_or_extremely_rare(
    population_frequency: PopulationFrequency, thresholds: PopulationRuleThresholds
) -> bool:
    observed_af = _observed_af(population_frequency)
    if population_frequency.is_absent:
        return True
    return observed_af <= thresholds.pm2_af_threshold


def _review_flags(
    context: GeneDiseaseContext,
    frequency: PopulationFrequency,
    thresholds: PopulationRuleThresholds,
) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    if context.disease_prevalence is None:
        flags.append(
            ReviewFlag(
                code="MISSING_DISEASE_PREVALENCE",
                message="Disease prevalence is missing; confidence is reduced and manual review is required.",
                blocking=True,
            )
        )
    if not thresholds.disease_specific:
        flags.append(
            ReviewFlag(
                code="MISSING_DISEASE_SPECIFIC_POPULATION_THRESHOLD",
                message=(
                    "Population-frequency thresholds are not marked disease-specific; "
                    "BA1/BS1/PM2 must remain candidate evidence pending review."
                ),
                blocking=True,
            )
        )
    if not thresholds.penetrance_provided:
        flags.append(
            ReviewFlag(
                code="MISSING_PENETRANCE_CONTEXT",
                message=(
                    "Penetrance context is missing; population evidence must remain "
                    "candidate-only pending review."
                ),
                blocking=True,
            )
        )
    if not context.inheritance_mode:
        flags.append(
            ReviewFlag(
                code="MISSING_INHERITANCE_MODE",
                message="Inheritance mode is missing; confidence is reduced and manual review is required.",
                blocking=True,
            )
        )
    if frequency.allele_number is not None and frequency.allele_number < thresholds.min_allele_number:
        flags.append(
            ReviewFlag(
                code="LOW_COVERAGE_POPULATION_FREQUENCY",
                message="Allele number is below the configured minimum for confident population-frequency interpretation.",
                blocking=True,
            )
        )
    if frequency.allele_number is None:
        flags.append(
            ReviewFlag(
                code="MISSING_ALLELE_NUMBER",
                message="Allele number is missing; population evidence must remain candidate-only.",
                blocking=True,
            )
        )
    if frequency.coverage_quality and frequency.coverage_quality.lower() in {
        "low",
        "poor",
        "insufficient",
        "failed",
    }:
        flags.append(
            ReviewFlag(
                code="LOW_COVERAGE_QUALITY",
                message="Population coverage quality is insufficient for automatic BA1/BS1/PM2 application.",
                blocking=True,
            )
        )
    if frequency.population_match is False:
        flags.append(
            ReviewFlag(
                code="POPULATION_MATCH_UNCONFIRMED",
                message="The population frequency record is not ancestry-matched to the provided context.",
                blocking=True,
            )
        )
    if frequency.limitations and frequency.overall_af is None and frequency.max_pop_af is None:
        flags.append(
            ReviewFlag(
                code="POPULATION_FREQUENCY_UNAVAILABLE",
                message="Population source limitations left frequency unavailable; absence must not be inferred.",
                blocking=True,
            )
        )
    population_name = frequency.population_name.lower()
    if any(founder in population_name for founder in thresholds.founder_populations):
        flags.append(
            ReviewFlag(
                code="FOUNDER_VARIANT_WARNING",
                message="Maximum population frequency is from a founder population; assess founder-effect context manually.",
                blocking=True,
            )
        )
    if context.population_ancestry and context.population_ancestry.lower() not in population_name:
        flags.append(
            ReviewFlag(
                code="POPULATION_MISMATCH_WARNING",
                message="Frequency population does not match the provided disease/context ancestry.",
                blocking=True,
            )
        )
    return flags


def _confidence(
    review_flags: list[ReviewFlag],
    context: GeneDiseaseContext,
    thresholds: PopulationRuleThresholds,
) -> float:
    confidence = thresholds.high_confidence
    if context.disease_prevalence is None or not context.inheritance_mode:
        confidence -= thresholds.missing_context_confidence_penalty
    warning_count = sum(1 for flag in review_flags if flag.code.endswith("_WARNING"))
    if warning_count:
        confidence -= thresholds.warning_confidence_penalty
    return max(0.0, min(1.0, confidence))


def _item(
    *,
    variant: Variant,
    code: EvidenceCode,
    strength: EvidenceStrength,
    direction: EvidenceDirection,
    reason: str,
    population_frequency: PopulationFrequency,
    confidence: float,
    review_flags: list[ReviewFlag],
    thresholds: PopulationRuleThresholds,
    candidate_only: bool,
) -> EvidenceItem:
    source = population_frequency.source or EvidenceSource(
        name=population_frequency.data_source,
        version=population_frequency.data_version,
        query={"variant_id": variant.variant_id},
    )
    digest = sha1(f"{variant.variant_id}:{code}:{population_frequency.data_source}".encode()).hexdigest()
    return EvidenceItem(
        evidence_id=f"ev-pop-{digest[:12]}",
        code=code,
        strength=EvidenceStrength.NONE if candidate_only else strength,
        direction=direction,
        reason=(
            f"Candidate-only population evidence: {reason}"
            if candidate_only
            else reason
        ),
        source=source,
        confidence=confidence,
        requires_review=True,
        triggered_by=["population_frequency"],
        supporting_data={
            "population_frequency": population_frequency.model_dump(mode="json"),
            "thresholds": thresholds.model_dump(mode="json"),
            "evidence_status": "candidate" if candidate_only else "applied",
            "candidate_only": candidate_only,
            "intended_strength": strength.value,
        },
        review_flags=review_flags,
    )
