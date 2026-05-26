from __future__ import annotations

from variant_pathogenicity_rater.acmg.population_rules import evaluate_population_rules
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.population.decision_tree import decide_population_evidence
from variant_pathogenicity_rater.population.schema import PopulationEvidenceDecision
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem, EvidenceStrength, PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


def generate_population_evidence(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    frequency: PopulationFrequency,
    thresholds: PopulationRuleThresholds,
    context_consistency: ContextConsistency | None = None,
    inheritance: str | None = None,
    disease_prevalence: float | None = None,
    penetrance: object | None = None,
    provider_provenance: dict[str, object] | None = None,
) -> tuple[list[EvidenceItem], PopulationEvidenceDecision]:
    provenance = dict(provider_provenance or {})
    provenance.setdefault("inheritance", inheritance or context.inheritance_mode)
    provenance.setdefault("disease_prevalence", disease_prevalence if disease_prevalence is not None else context.disease_prevalence)
    provenance.setdefault("penetrance_provided", penetrance is not None or thresholds.penetrance_provided)

    decision = decide_population_evidence(
        variant=variant,
        context=context,
        frequency=frequency,
        thresholds=thresholds,
        context_consistency=context_consistency,
        provenance=provenance,
    )
    if decision.recommended_code is None:
        return [], decision

    items = evaluate_population_rules(variant, context, frequency, thresholds)
    matching = [item for item in items if str(item.code) == decision.recommended_code]
    if not matching:
        return [], decision

    item = matching[0]
    supporting_data = dict(item.supporting_data)
    supporting_data["population_evidence_decision"] = decision.model_dump(mode="json")
    supporting_data["decision_path"] = list(decision.decision_path)
    supporting_data["quality_checks"] = [check.model_dump(mode="json") for check in decision.quality_checks]
    supporting_data["blocking_reasons"] = list(decision.blocking_reasons)
    supporting_data["downgrade_reasons"] = list(decision.downgrade_reasons)
    supporting_data["limitations"] = list(decision.limitations)
    supporting_data["applied"] = decision.applied
    supporting_data["candidate_only"] = decision.candidate_only
    supporting_data["evidence_status"] = "applied" if decision.applied else "candidate"
    item.supporting_data = supporting_data
    item.requires_review = True
    item.applied = decision.applied
    item.candidate_only = decision.candidate_only
    if decision.candidate_only:
        item.strength = EvidenceStrength.NONE
        if not item.reason.startswith("Candidate-only population evidence:"):
            item.reason = f"Candidate-only population evidence: {item.reason}"
    item.reason = _rationale(item.reason, frequency, decision)
    return [item], decision


def _rationale(reason: str, frequency: PopulationFrequency, decision: PopulationEvidenceDecision) -> str:
    af = max(value for value in [frequency.overall_af, frequency.max_pop_af] if value is not None)
    threshold = decision.thresholds_used.get("ba1_af_threshold")
    if decision.recommended_code == "BS1":
        threshold = decision.thresholds_used.get("bs1_af_threshold")
    if decision.recommended_code == "PM2":
        threshold = decision.thresholds_used.get("pm2_af_threshold")
    status = "applied" if decision.applied else "candidate-only"
    return (
        f"{reason} Population decision: {status}; observed AF {af:g} in "
        f"{frequency.population_name}; threshold used {threshold}; quality checks "
        f"{_quality_summary(decision)}."
    )


def _quality_summary(decision: PopulationEvidenceDecision) -> str:
    passed = [check.name for check in decision.quality_checks if check.passed]
    failed = [check.name for check in decision.quality_checks if not check.passed]
    if failed:
        return "passed " + ", ".join(passed) + "; failed " + ", ".join(failed)
    return "passed " + ", ".join(passed)

