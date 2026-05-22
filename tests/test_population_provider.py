from __future__ import annotations

import json

from variant_pathogenicity_rater.acmg.population_rules import evaluate_population_rules
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.providers import build_population_provider
from variant_pathogenicity_rater.schemas import (
    EvidenceCode,
    EvidenceStrength,
    GeneDiseaseContext,
    Variant,
)


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
        hgvs_c="NM_000001.1:c.76A>G",
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


def _thresholds() -> PopulationRuleThresholds:
    return PopulationRuleThresholds(disease_specific=True, penetrance_provided=True)


def _provider(tmp_path, records: list[dict[str, object]]):
    local_file = tmp_path / "population.jsonl"
    local_file.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )
    return build_population_provider(
        DataSourceConfig(
            name="population",
            mode="local_file",
            source_version="gnomad-like-test-v1",
            parser_version="population-parser-test",
            cache_dir=str(tmp_path / "cache"),
            local_file=str(local_file),
        )
    )


def _record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "variant_key": "1-100-A-G",
        "genome_build": "GRCh38",
        "dataset_version": "gnomad-like-test-v1",
        "overall_af": 0.0,
        "max_pop_af": 0.0,
        "population_name": "global",
        "allele_count": 0,
        "allele_number": 100000,
        "homozygote_count": 0,
        "hemizygote_count": 0,
        "faf95": 0.0,
        "filtering_af": 0.0,
        "coverage_quality": "high",
        "population_match": True,
    }
    payload.update(overrides)
    return payload


def test_local_file_hit_attaches_population_provenance(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record()]).query(_variant())

    assert frequency.overall_af == 0.0
    assert frequency.dataset_version == "gnomad-like-test-v1"
    assert frequency.coverage_quality == "high"
    assert frequency.population_match is True
    assert frequency.source is not None
    provenance = frequency.source.provenance
    assert provenance.data_source == "population"
    assert provenance.source_version == "gnomad-like-test-v1"
    assert provenance.query["chrom"] == "1"
    assert provenance.retrieved_at
    assert provenance.raw_record_hash
    assert provenance.parser_version == "population-parser-test"
    assert provenance.population == "global"
    assert provenance.allele_number == 100000
    assert provenance.coverage_quality == "high"
    assert provenance.limitations


def test_local_file_gene_hgvs_fallback_hit(tmp_path) -> None:
    frequency = _provider(
        tmp_path,
        [
            _record(
                variant_key="2-200-C-T",
                gene="GENE1",
                hgvs_c="NM_000001.1:c.76A>G",
                overall_af=0.02,
                max_pop_af=0.02,
                allele_count=2000,
            )
        ],
    ).query(_variant())

    assert frequency.overall_af == 0.02
    assert frequency.allele_count == 2000


def test_local_file_miss_does_not_imply_absence_or_pm2(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(variant_key="1-101-A-G")]).query(_variant())
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert frequency.overall_af is None
    assert frequency.is_absent is False
    assert any("must not be interpreted as absence" in item for item in frequency.limitations)
    assert items == []


def test_malformed_local_population_record_becomes_limitation(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(allele_number=-1)]).query(_variant())
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert frequency.overall_af is None
    assert any("could not be parsed" in item for item in frequency.limitations)
    assert items == []


def test_genome_build_mismatch_is_limitation_not_frequency(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(genome_build="GRCh37")]).query(_variant())
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert frequency.overall_af is None
    assert any("different genome build" in item for item in frequency.limitations)
    assert items == []


def test_low_allele_number_is_candidate_only(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(overall_af=0.06, max_pop_af=0.06, allele_number=100)]).query(
        _variant()
    )
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert items[0].code == EvidenceCode.BA1
    assert items[0].strength == EvidenceStrength.NONE
    assert items[0].supporting_data["evidence_status"] == "candidate"


def test_low_coverage_is_candidate_only(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(overall_af=0.02, max_pop_af=0.02, coverage_quality="low")]).query(
        _variant()
    )
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert items[0].code == EvidenceCode.BS1
    assert items[0].strength == EvidenceStrength.NONE
    assert {flag.code for flag in items[0].review_flags} >= {"LOW_COVERAGE_QUALITY"}


def test_ancestry_mismatch_is_candidate_only(tmp_path) -> None:
    frequency = _provider(
        tmp_path,
        [_record(overall_af=0.02, max_pop_af=0.02, population_name="European", population_match=False)],
    ).query(_variant())
    items = evaluate_population_rules(
        _variant(),
        _context(population_ancestry="East Asian"),
        frequency,
        _thresholds(),
    )

    assert items[0].strength == EvidenceStrength.NONE
    assert "POPULATION_MISMATCH_WARNING" in {flag.code for flag in items[0].review_flags}


def test_zero_af_high_quality_context_applies_pm2_supporting(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record()]).query(_variant())
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert items[0].code == EvidenceCode.PM2
    assert items[0].strength == EvidenceStrength.SUPPORTING
    assert items[0].supporting_data["evidence_status"] == "applied"


def test_zero_af_without_context_is_candidate_only(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record()]).query(_variant())
    items = evaluate_population_rules(
        _variant(),
        _context(disease_prevalence=None),
        frequency,
        _thresholds(),
    )

    assert items[0].code == EvidenceCode.PM2
    assert items[0].strength == EvidenceStrength.NONE


def test_high_af_with_valid_context_applies_ba1(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(overall_af=0.06, max_pop_af=0.06, allele_count=6000)]).query(
        _variant()
    )
    items = evaluate_population_rules(_variant(), _context(), frequency, _thresholds())

    assert items[0].code == EvidenceCode.BA1
    assert items[0].strength == EvidenceStrength.STAND_ALONE


def test_high_af_without_context_is_candidate_only(tmp_path) -> None:
    frequency = _provider(tmp_path, [_record(overall_af=0.06, max_pop_af=0.06, allele_count=6000)]).query(
        _variant()
    )
    items = evaluate_population_rules(
        _variant(),
        _context(inheritance_mode=None),
        frequency,
        _thresholds(),
    )

    assert items[0].code == EvidenceCode.BA1
    assert items[0].strength == EvidenceStrength.NONE
