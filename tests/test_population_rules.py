from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from variant_pathogenicity_rater.acmg.population_rules import evaluate_population_rules
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.evidence.population import MockPopulationFrequencyProvider
from variant_pathogenicity_rater.schemas import (
    EvidenceCode,
    EvidenceDirection,
    EvidenceStrength,
    GeneDiseaseContext,
    PopulationFrequency,
    Variant,
)


ROOT = Path(__file__).resolve().parents[1]


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
    }
    payload.update(overrides)
    return GeneDiseaseContext.model_validate(payload)


def _frequency(**overrides: object) -> PopulationFrequency:
    payload = {
        "overall_af": 0.0,
        "max_pop_af": 0.0,
        "population_name": "global",
        "allele_count": 0,
        "allele_number": 100000,
        "homozygote_count": 0,
        "hemizygote_count": 0,
        "data_source": "mock_population_frequency",
        "is_absent": False,
    }
    payload.update(overrides)
    return PopulationFrequency.model_validate(payload)


def test_ba1_triggers_stand_alone_benign() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(),
        _frequency(overall_af=0.06, max_pop_af=0.06, allele_count=6000),
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert len(items) == 1
    assert items[0].code == EvidenceCode.BA1
    assert items[0].strength == EvidenceStrength.STAND_ALONE
    assert items[0].direction == EvidenceDirection.BENIGN


def test_bs1_triggers_strong_benign_below_ba1() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(),
        _frequency(overall_af=0.02, max_pop_af=0.02, allele_count=2000),
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert len(items) == 1
    assert items[0].code == EvidenceCode.BS1
    assert items[0].strength == EvidenceStrength.STRONG


def test_pm2_triggers_supporting_pathogenic_for_absent_variant() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(),
        _frequency(is_absent=True),
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert len(items) == 1
    assert items[0].code == EvidenceCode.PM2
    assert items[0].strength == EvidenceStrength.SUPPORTING
    assert items[0].direction == EvidenceDirection.PATHOGENIC


def test_ba1_and_pm2_do_not_trigger_together() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(),
        _frequency(overall_af=0.06, max_pop_af=0.06, is_absent=True),
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert [item.code for item in items] == [EvidenceCode.BA1]


def test_missing_context_lowers_confidence_and_requires_review_flags() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(disease_prevalence=None, inheritance_mode=None),
        _frequency(is_absent=True),
    )

    assert items[0].supporting_data["evidence_status"] == "candidate"
    assert items[0].strength == EvidenceStrength.NONE
    assert {
        "MISSING_DISEASE_PREVALENCE",
        "MISSING_INHERITANCE_MODE",
    }.issubset({flag.code for flag in items[0].review_flags})


def test_population_warnings_are_recorded() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(population_ancestry="east asian"),
        _frequency(
            overall_af=0.02,
            max_pop_af=0.02,
            population_name="Finnish",
            allele_number=100,
        ),
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    flag_codes = {flag.code for flag in items[0].review_flags}
    assert "FOUNDER_VARIANT_WARNING" in flag_codes
    assert "LOW_COVERAGE_POPULATION_FREQUENCY" in flag_codes
    assert "POPULATION_MISMATCH_WARNING" in flag_codes
    assert items[0].supporting_data["evidence_status"] == "candidate"


def test_thresholds_are_configurable() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(),
        _frequency(overall_af=0.006, max_pop_af=0.006),
        PopulationRuleThresholds(
            bs1_af_threshold=0.005,
            disease_specific=True,
            penetrance_provided=True,
        ),
    )

    assert items[0].code == EvidenceCode.BS1


def test_mock_population_provider_returns_population_frequency() -> None:
    frequency = MockPopulationFrequencyProvider().query(_variant())

    assert frequency.data_source == "mock_population_frequency"
    assert frequency.is_absent is False
    assert frequency.overall_af is None


def test_observed_af_none_does_not_trigger_pm2() -> None:
    items = evaluate_population_rules(
        _variant(),
        _context(),
        _frequency(overall_af=None, max_pop_af=None, is_absent=True),
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert items == []


def test_mock_population_provider_without_fixture_does_not_trigger_pm2() -> None:
    frequency = MockPopulationFrequencyProvider().query(_variant())
    items = evaluate_population_rules(
        _variant(),
        _context(),
        frequency,
        PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert items == []


def test_population_context_insufficient_makes_ba1_bs1_pm2_candidate_only() -> None:
    for frequency in [
        _frequency(overall_af=0.06, max_pop_af=0.06),
        _frequency(overall_af=0.02, max_pop_af=0.02),
        _frequency(overall_af=0.0, max_pop_af=0.0, is_absent=True),
    ]:
        items = evaluate_population_rules(_variant(), _context(), frequency)

        assert len(items) == 1
        assert items[0].strength == EvidenceStrength.NONE
        assert items[0].supporting_data["evidence_status"] == "candidate"


def test_query_population_frequency_mcp_tool_uses_mock_provider() -> None:
    module_path = ROOT / "mcp-server" / "tools" / "rate_variant.py"
    sys.path.insert(0, str(ROOT / "mcp-server"))
    spec = importlib.util.spec_from_file_location("rate_variant_tool", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = asyncio.run(
        module.query_population_frequency({"variant": json.loads(_variant().model_dump_json())})
    )

    assert result["status"] == "ok"
    assert result["population_frequency"]["data_source"] == "mock_population_frequency"
