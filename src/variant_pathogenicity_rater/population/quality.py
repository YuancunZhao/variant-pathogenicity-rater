from __future__ import annotations

from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.population.schema import PopulationQualityCheck
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


LOW_CONFIDENCE_FILTERS = {"fail", "failed", "low_confidence", "low confidence", "qc_fail", "qc fail"}
LOW_COVERAGE_VALUES = {"low", "poor", "insufficient", "failed"}
ADEQUATE_COVERAGE_VALUES = {"high", "adequate", "pass", "passed", "medium", "good"}


def population_quality_checks(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    frequency: PopulationFrequency,
    thresholds: PopulationRuleThresholds,
    context_consistency: ContextConsistency | None = None,
) -> list[PopulationQualityCheck]:
    checks: list[PopulationQualityCheck] = []
    source_version = _source_version(frequency)
    observed_build = frequency.genome_build
    coverage = (frequency.coverage_quality or "").strip().lower()
    population_name = frequency.population_name.lower()
    ancestry = (context.population_ancestry or "").strip().lower()

    checks.append(
        PopulationQualityCheck(
            name="allele_number_sufficient",
            passed=frequency.allele_number is not None
            and frequency.allele_number >= thresholds.min_allele_number,
            observed=frequency.allele_number,
            expected=f">= {thresholds.min_allele_number}",
            reason="Allele number must be present and meet the configured minimum.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="coverage_quality_adequate",
            passed=bool(coverage) and coverage not in LOW_COVERAGE_VALUES,
            observed=frequency.coverage_quality,
            expected="not low/poor/insufficient/failed",
            reason="Population coverage quality must be adequate for automatic evidence.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="population_match",
            passed=frequency.population_match is True,
            observed=frequency.population_match,
            expected=True,
            reason="Provider must explicitly mark the record as population matched.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="ancestry_match",
            passed=not ancestry or ancestry == "global" or ancestry in population_name,
            observed=frequency.population_name,
            expected=context.population_ancestry or "no ancestry constraint supplied",
            reason="Frequency population must match the provided ancestry context.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="genome_build_match",
            passed=observed_build is not None and str(observed_build) == str(variant.genome_build),
            observed=observed_build,
            expected=str(variant.genome_build),
            reason="Population provider genome build must match the normalized variant.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="source_version_present",
            passed=bool(source_version),
            observed=source_version,
            expected="provider source version",
            reason="Population source version/provenance must be retained.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="provider_confidence_flags",
            passed=(frequency.filter_status or "").strip().lower() not in LOW_CONFIDENCE_FILTERS,
            observed=frequency.filter_status,
            expected="no low-confidence filter flags",
            reason="Low-confidence provider flags block automatic population evidence.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="founder_population_absent",
            passed=not any(founder in population_name for founder in thresholds.founder_populations),
            observed=frequency.population_name,
            expected="not a configured founder population",
            reason="Founder-population signals require manual founder-effect review.",
        )
    )
    checks.append(
        PopulationQualityCheck(
            name="context_conflict_absent",
            passed=context_consistency is None or context_consistency.status != "conflict",
            observed=context_consistency.status if context_consistency else None,
            expected="not conflict",
            reason="Context conflicts block automatic population evidence.",
        )
    )
    return checks


def quality_blocking_reasons(checks: list[PopulationQualityCheck]) -> list[str]:
    return [f"{check.name}: {check.reason}" for check in checks if check.blocking and not check.passed]


def _source_version(frequency: PopulationFrequency) -> str | None:
    if frequency.source and frequency.source.version:
        return frequency.source.version
    return frequency.data_version or frequency.dataset_version
