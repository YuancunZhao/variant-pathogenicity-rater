from __future__ import annotations

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.population import generate_population_evidence
from variant_pathogenicity_rater.schemas import GeneDiseaseContext, PopulationFrequency, Variant
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency, ContextConsistencyCheck


def _variant() -> Variant:
    return Variant(
        variant_id="GRCh38-1-100-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=100,
        ref="A",
        alt="G",
        gene_symbol="GENE1",
    )


def _context(**overrides: object) -> GeneDiseaseContext:
    payload = {
        "gene_symbol": "GENE1",
        "disease_name": "Example disease",
        "inheritance_mode": "autosomal dominant",
        "disease_prevalence": 0.0001,
        "population_ancestry": "global",
    }
    payload.update(overrides)
    return GeneDiseaseContext.model_validate(payload)


def _thresholds(**overrides: object) -> PopulationRuleThresholds:
    payload = {"disease_specific": True, "penetrance_provided": True}
    payload.update(overrides)
    return PopulationRuleThresholds.model_validate(payload)


def _frequency(**overrides: object) -> PopulationFrequency:
    payload = {
        "overall_af": 0.0,
        "max_pop_af": 0.0,
        "population_name": "global",
        "allele_count": 0,
        "allele_number": 100000,
        "homozygote_count": 0,
        "hemizygote_count": 0,
        "data_source": "test_population",
        "data_version": "test-v1",
        "is_absent": True,
        "coverage_quality": "high",
        "population_match": True,
        "genome_build": "GRCh38",
    }
    payload.update(overrides)
    return PopulationFrequency.model_validate(payload)


def _generate(
    frequency: PopulationFrequency,
    *,
    context: GeneDiseaseContext | None = None,
    thresholds: PopulationRuleThresholds | None = None,
    consistency: ContextConsistency | None = None,
):
    return generate_population_evidence(
        variant=_variant(),
        context=context or _context(),
        frequency=frequency,
        thresholds=thresholds or _thresholds(),
        context_consistency=consistency,
    )


def test_no_record_found_does_not_generate_pm2() -> None:
    items, decision = _generate(
        _frequency(overall_af=None, max_pop_af=None, is_absent=False, allele_number=None)
    )

    assert items == []
    assert decision.recommended_code is None
    assert any("No population record found" in item for item in decision.limitations)


def test_zero_af_sufficient_an_and_disease_context_applies_pm2_supporting() -> None:
    items, decision = _generate(_frequency())

    assert decision.applied is True
    assert items[0].code == "PM2"
    assert items[0].strength == "supporting"
    assert items[0].requires_review is True
    assert items[0].supporting_data["population_evidence_decision"]["applied"] is True


def test_zero_af_but_low_an_is_candidate_only() -> None:
    items, decision = _generate(_frequency(allele_number=100))

    assert decision.candidate_only is True
    assert items[0].code == "PM2"
    assert items[0].strength == "none"
    assert items[0].applied is False


def test_zero_af_but_ancestry_mismatch_is_candidate_only() -> None:
    items, decision = _generate(
        _frequency(population_name="European", population_match=False),
        context=_context(population_ancestry="East Asian"),
    )

    assert decision.candidate_only is True
    assert items[0].code == "PM2"
    assert items[0].candidate_only is True


def test_high_af_with_valid_ba1_threshold_applies_ba1() -> None:
    items, decision = _generate(_frequency(overall_af=0.08, max_pop_af=0.08, is_absent=False))

    assert decision.applied is True
    assert items[0].code == "BA1"
    assert items[0].strength == "stand_alone"


def test_high_af_without_disease_threshold_is_candidate_only() -> None:
    items, decision = _generate(
        _frequency(overall_af=0.08, max_pop_af=0.08, is_absent=False),
        thresholds=PopulationRuleThresholds(disease_specific=False, penetrance_provided=True),
    )

    assert decision.candidate_only is True
    assert items[0].code == "BA1"
    assert items[0].strength == "none"


def test_bs1_applied_with_configured_threshold() -> None:
    items, decision = _generate(_frequency(overall_af=0.02, max_pop_af=0.02, is_absent=False))

    assert decision.applied is True
    assert items[0].code == "BS1"
    assert items[0].strength == "strong"


def test_founder_warning_blocks_applied() -> None:
    items, decision = _generate(
        _frequency(overall_af=0.02, max_pop_af=0.02, is_absent=False, population_name="Finnish")
    )

    assert decision.candidate_only is True
    assert items[0].strength == "none"
    assert any("founder_population_absent" in item for item in decision.blocking_reasons)


def test_genome_build_mismatch_blocks_applied() -> None:
    items, decision = _generate(_frequency(overall_af=0.02, max_pop_af=0.02, is_absent=False, genome_build="GRCh37"))

    assert decision.candidate_only is True
    assert items[0].strength == "none"
    assert any("genome_build_match" in item for item in decision.blocking_reasons)


def test_context_conflict_blocks_applied() -> None:
    consistency = ContextConsistency(
        status="conflict",
        conflicts=[
            ContextConsistencyCheck(
                check_name="provider_genome_build_vs_input_genome_build",
                severity="conflict",
                field="genome_build",
                expected="GRCh38",
                observed="GRCh37",
                reason="Genome build mismatch.",
                source="population",
            )
        ],
    )

    items, decision = _generate(
        _frequency(overall_af=0.02, max_pop_af=0.02, is_absent=False),
        consistency=consistency,
    )

    assert decision.candidate_only is True
    assert items[0].strength == "none"
    assert any("context_conflict_absent" in item for item in decision.blocking_reasons)


def test_candidate_population_evidence_does_not_alter_classification() -> None:
    items, _decision = _generate(
        _frequency(overall_af=0.08, max_pop_af=0.08, is_absent=False),
        thresholds=PopulationRuleThresholds(disease_specific=False, penetrance_provided=True),
    )
    result = classify_acmg(items, _variant(), _context())

    assert result.final_classification == "vus"


def test_applied_ba1_affects_classification_only_via_combiner() -> None:
    items, _decision = _generate(_frequency(overall_af=0.08, max_pop_af=0.08, is_absent=False))
    result = classify_acmg(items, _variant(), _context())

    assert result.final_classification == "benign"
    assert result.applied_combination_rule == "benign: BA1 stand_alone"


def test_report_includes_af_threshold_and_population_decision_path() -> None:
    payload = {
        "gene": "GENE1",
        "chromosome": "1",
        "position": 100,
        "ref": "A",
        "alt": "G",
        "disease": "Example disease",
        "inheritance": "autosomal dominant",
        "gene_disease_context": _context().model_dump(mode="json"),
        "options": {
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "population_frequency": {
                **_frequency(overall_af=0.02, max_pop_af=0.02, is_absent=False).model_dump(mode="json"),
                "variant_id": "GRCh38-1-100-A-G",
            },
            "population_thresholds": _thresholds().model_dump(mode="json"),
        },
    }

    result = rate_variant(payload)

    assert result["status"] == "ok"
    assert "Population decision path" in result["report_text"]
    assert "observed AF 0.02" in result["report_text"]
    assert "threshold" in result["report_text"]

