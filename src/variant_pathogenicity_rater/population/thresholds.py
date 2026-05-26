from __future__ import annotations

from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds


def thresholds_used(thresholds: PopulationRuleThresholds) -> dict[str, object]:
    return thresholds.model_dump(mode="json")


def has_disease_specific_thresholds(thresholds: PopulationRuleThresholds) -> bool:
    return bool(thresholds.disease_specific and thresholds.penetrance_provided)

