from __future__ import annotations

from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.population.quality import population_quality_checks
from variant_pathogenicity_rater.population.safety import (
    applied_blocking_reasons,
    no_record_found,
    observed_af,
)
from variant_pathogenicity_rater.population.schema import PopulationEvidenceDecision
from variant_pathogenicity_rater.population.thresholds import thresholds_used
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


def decide_population_evidence(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    frequency: PopulationFrequency,
    thresholds: PopulationRuleThresholds,
    context_consistency: ContextConsistency | None = None,
    provenance: dict[str, object] | None = None,
) -> PopulationEvidenceDecision:
    checks = population_quality_checks(
        variant=variant,
        context=context,
        frequency=frequency,
        thresholds=thresholds,
        context_consistency=context_consistency,
    )
    path: list[str] = ["Start population evidence decision."]
    af = observed_af(frequency)

    if no_record_found(frequency):
        path.append("No population frequency record or usable AF was found; do not infer absence.")
        return PopulationEvidenceDecision(
            decision_path=path,
            thresholds_used=thresholds_used(thresholds),
            quality_checks=checks,
            blocking_reasons=applied_blocking_reasons(
                context=context,
                frequency=frequency,
                thresholds=thresholds,
                quality_checks=checks,
            ),
            limitations=[
                "No population record found is not evidence of absence and cannot trigger PM2_Supporting."
            ],
            provenance=provenance or _provenance(frequency),
        )

    code: str | None = None
    strength = "none"
    direction = "neutral"
    if af is not None and af >= thresholds.ba1_af_threshold:
        code = "BA1"
        strength = "stand_alone"
        direction = "benign"
        path.append(f"Observed AF {af:g} meets BA1 threshold {thresholds.ba1_af_threshold:g}.")
    elif af is not None and af >= thresholds.bs1_af_threshold:
        code = "BS1"
        strength = "strong"
        direction = "benign"
        path.append(f"Observed AF {af:g} meets BS1 threshold {thresholds.bs1_af_threshold:g}.")
    elif af is not None and (
        frequency.is_absent or af <= thresholds.pm2_af_threshold
    ):
        code = "PM2"
        strength = "supporting"
        direction = "pathogenic"
        path.append(f"Observed AF {af:g} is zero/very-low at or below PM2 threshold {thresholds.pm2_af_threshold:g}.")
    else:
        path.append(f"Observed AF {af:g} does not meet BA1, BS1, or PM2_Supporting thresholds.")

    blockers = applied_blocking_reasons(
        context=context,
        frequency=frequency,
        thresholds=thresholds,
        quality_checks=checks,
    )
    applied = code is not None and not blockers
    candidate_only = code is not None and not applied
    if applied:
        path.append(f"{code} may be applied; all population quality and disease-context gates passed.")
    elif code:
        path.append(f"{code} remains candidate-only because one or more safety gates failed.")

    return PopulationEvidenceDecision(
        recommended_code=code,
        strength=strength if applied else ("none" if candidate_only else "none"),
        direction=direction,
        applied=applied,
        candidate_only=candidate_only,
        decision_path=path,
        thresholds_used=thresholds_used(thresholds),
        quality_checks=checks,
        blocking_reasons=blockers if code else [],
        downgrade_reasons=blockers if candidate_only else [],
        limitations=list(frequency.limitations),
        provenance=provenance or _provenance(frequency),
    )


def _provenance(frequency: PopulationFrequency) -> dict[str, object]:
    return {
        "data_source": frequency.data_source,
        "data_version": frequency.data_version or frequency.dataset_version,
        "source": frequency.source.model_dump(mode="json") if frequency.source else None,
    }

