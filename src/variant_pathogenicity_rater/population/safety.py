from __future__ import annotations

from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.population.quality import quality_blocking_reasons
from variant_pathogenicity_rater.population.schema import PopulationQualityCheck
from variant_pathogenicity_rater.population.thresholds import has_disease_specific_thresholds
from variant_pathogenicity_rater.schemas.evidence import PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext


def no_record_found(frequency: PopulationFrequency) -> bool:
    return frequency.overall_af is None and frequency.max_pop_af is None


def observed_af(frequency: PopulationFrequency) -> float | None:
    values = [value for value in [frequency.overall_af, frequency.max_pop_af] if value is not None]
    return max(values) if values else None


def disease_context_complete(context: GeneDiseaseContext, thresholds: PopulationRuleThresholds) -> bool:
    return bool(
        context.disease_name
        and context.disease_name != "not provided"
        and context.inheritance_mode
        and context.disease_prevalence is not None
        and has_disease_specific_thresholds(thresholds)
    )


def applied_blocking_reasons(
    *,
    context: GeneDiseaseContext,
    frequency: PopulationFrequency,
    thresholds: PopulationRuleThresholds,
    quality_checks: list[PopulationQualityCheck],
) -> list[str]:
    reasons = quality_blocking_reasons(quality_checks)
    if not disease_context_complete(context, thresholds):
        reasons.append(
            "disease_context_complete: disease, inheritance, prevalence, penetrance, and disease-specific thresholds are required."
        )
    if no_record_found(frequency):
        reasons.append("no_record_found: provider miss or unavailable AF must not be interpreted as population absence.")
    return list(dict.fromkeys(reasons))

