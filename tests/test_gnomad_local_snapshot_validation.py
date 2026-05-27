from __future__ import annotations

import asyncio
import json
from pathlib import Path

from config import ServerConfig
from server import McpServer, build_registry
from variant_pathogenicity_rater.cli import main
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.providers import build_population_provider
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pipeline.real_world import run_annotation_batch_workflow
from variant_pathogenicity_rater.population import generate_population_evidence
from variant_pathogenicity_rater.schemas import EvidenceStrength, GeneDiseaseContext, Variant


FIXTURE = Path("data/fixtures/gnomad_local_snapshot_validation.jsonl")


def _server() -> McpServer:
    config = ServerConfig(
        server_name="variant-pathogenicity-rater-test",
        server_version="0.1.0",
        log_level="ERROR",
        tools_package="tools",
        enable_health_tool=True,
        environment="test",
    )
    return McpServer(config, build_registry(config))


def _variant(pos: int, *, alt: str = "G") -> Variant:
    return Variant(
        variant_id=f"GRCh38-1-{pos}-A-{alt}",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=pos,
        ref="A",
        alt=alt,
        gene_symbol="GENE1",
        hgvs_c=f"NM_000001.1:c.{pos}A>{alt}",
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


def _context_input(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "gene": "GENE1",
        "disease": "Example disease",
        "inheritance": "autosomal dominant",
        "disease_prevalence": 0.0001,
        "population_ancestry": "global",
    }
    payload.update(overrides)
    return payload


def _thresholds(**overrides: object) -> PopulationRuleThresholds:
    payload = {"disease_specific": True, "penetrance_provided": True}
    payload.update(overrides)
    return PopulationRuleThresholds.model_validate(payload)


def _provider(tmp_path, *, source_version: str | None = "gnomad-local-validation-v1"):
    return build_population_provider(
        DataSourceConfig(
            name="population",
            mode="local_file",
            source_version=source_version,
            parser_version="population-parser-validation-test",
            cache_dir=str(tmp_path / "cache"),
            local_file=str(FIXTURE),
        )
    )


def _generate(tmp_path, pos: int, *, context: GeneDiseaseContext | None = None, source_version: str | None = "gnomad-local-validation-v1"):
    variant = _variant(pos)
    frequency = _provider(tmp_path, source_version=source_version).query(variant)
    return generate_population_evidence(
        variant=variant,
        context=context or _context(),
        frequency=frequency,
        thresholds=_thresholds(),
    )


def _rate_payload(tmp_path, pos: int, *, cache_name: str = "rate-cache") -> dict[str, object]:
    return {
        "gene": "GENE1",
        "chromosome": "1",
        "position": pos,
        "ref": "A",
        "alt": "G",
        "disease": "Example disease",
        "inheritance": "autosomal dominant",
        "gene_disease_context": _context_input(),
        "options": {
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "population_thresholds": _thresholds().model_dump(mode="json"),
            "data_sources": {
                "sources": {
                    "population": {
                        "mode": "local_file",
                        "local_file": str(FIXTURE),
                        "source_version": "gnomad-local-validation-v1",
                        "parser_version": "population-parser-validation-test",
                        "cache_dir": str(tmp_path / cache_name),
                    }
                }
            },
        },
    }


def test_fixture_preserves_required_gnomad_like_fields() -> None:
    required = {
        "chromosome",
        "position",
        "ref",
        "alt",
        "genome_build",
        "overall_af",
        "max_pop_af",
        "faf95",
        "filtering_af",
        "allele_count",
        "allele_number",
        "homozygote_count",
        "hemizygote_count",
        "population_name",
        "coverage_quality",
        "population_match",
        "source_version",
    }
    records = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    usable = [record for record in records if record["scenario"] != "missing_source_version"]

    assert records
    assert all(required.issubset(record) for record in usable)


def test_no_record_found_is_limitation_only_and_not_pm2(tmp_path) -> None:
    items, decision = _generate(tmp_path, 999)

    assert items == []
    assert decision.recommended_code is None
    assert any("not evidence of absence" in item for item in decision.limitations)


def test_zero_af_high_an_applies_pm2_supporting(tmp_path) -> None:
    items, decision = _generate(tmp_path, 100)

    assert decision.applied is True
    assert items[0].code == "PM2"
    assert items[0].strength == EvidenceStrength.SUPPORTING
    assert items[0].requires_review is True


def test_zero_af_low_an_is_candidate_only(tmp_path) -> None:
    items, decision = _generate(tmp_path, 101)

    assert decision.candidate_only is True
    assert items[0].code == "PM2"
    assert items[0].strength == EvidenceStrength.NONE
    assert any("allele_number_sufficient" in reason for reason in decision.blocking_reasons)


def test_ba1_and_bs1_require_configured_disease_specific_thresholds(tmp_path) -> None:
    ba1_items, ba1_decision = _generate(tmp_path, 102)
    bs1_items, bs1_decision = _generate(tmp_path, 103)

    assert ba1_decision.applied is True
    assert ba1_items[0].code == "BA1"
    assert bs1_decision.applied is True
    assert bs1_items[0].code == "BS1"

    frequency = _provider(tmp_path).query(_variant(102))
    candidate_items, candidate_decision = generate_population_evidence(
        variant=_variant(102),
        context=_context(),
        frequency=frequency,
        thresholds=PopulationRuleThresholds(disease_specific=False, penetrance_provided=True),
    )
    assert candidate_decision.candidate_only is True
    assert candidate_items[0].strength == EvidenceStrength.NONE
    assert any("disease_context_complete" in reason for reason in candidate_decision.blocking_reasons)


def test_quality_and_context_mismatches_are_candidate_or_limitation(tmp_path) -> None:
    cases = {
        104: "population_match",
        105: "coverage_quality_adequate",
        107: "founder_population_absent",
    }
    for pos, blocker in cases.items():
        context = _context(population_ancestry="East Asian") if pos == 104 else _context()
        items, decision = _generate(tmp_path, pos, context=context)
        assert decision.candidate_only is True
        assert items[0].strength == EvidenceStrength.NONE
        assert any(blocker in reason for reason in decision.blocking_reasons)


def test_genome_build_mismatch_malformed_and_unsupported_rows_are_limitation_only(tmp_path) -> None:
    for pos, expected in {
        106: "different genome build",
        109: "could not be parsed",
        110: "unsupported symbolic or multiallelic alleles",
        111: "unsupported symbolic or multiallelic alleles",
    }.items():
        frequency = _provider(tmp_path).query(_variant(pos))
        items, decision = generate_population_evidence(
            variant=_variant(pos),
            context=_context(),
            frequency=frequency,
            thresholds=_thresholds(),
        )
        assert frequency.overall_af is None
        assert items == []
        assert decision.recommended_code is None
        assert any(expected in limitation for limitation in frequency.limitations + decision.limitations)


def test_missing_source_version_is_candidate_only(tmp_path) -> None:
    items, decision = _generate(tmp_path, 108, source_version=None)

    assert decision.candidate_only is True
    assert items[0].strength == EvidenceStrength.NONE
    assert any("source_version_present" in reason for reason in decision.blocking_reasons)


def test_local_provider_failure_returns_limitation_not_exception(tmp_path) -> None:
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{not json", encoding="utf-8")
    provider = build_population_provider(
        DataSourceConfig(
            name="population",
            mode="local_file",
            source_version="broken-snapshot-v1",
            parser_version="population-parser-validation-test",
            cache_dir=str(tmp_path / "broken-cache"),
            local_file=str(broken),
        )
    )

    frequency = provider.query(_variant(100))

    assert frequency.overall_af is None
    assert frequency.is_absent is False
    assert any("local-file query failed" in limitation for limitation in frequency.limitations)


def test_rate_variant_local_snapshot_applied_candidate_and_report_paths(tmp_path) -> None:
    applied = rate_variant(_rate_payload(tmp_path, 102, cache_name="rate-applied"))
    candidate = rate_variant(_rate_payload(tmp_path, 105, cache_name="rate-candidate"))

    assert applied["status"] == "ok"
    assert [item["code"] for item in applied["applied_evidence"]] == ["BA1"]
    assert applied["step_results"]["query_population_frequency"]["source"]["provenance"]["raw_record_hash"]
    assert applied["step_results"]["evaluate_population_evidence"]["decision"]["applied"] is True
    assert "Population decision path" in applied["report_text"]
    assert "threshold" in applied["report_text"]

    assert candidate["status"] == "ok"
    assert [item["code"] for item in candidate["review_note_evidence"]] == ["BS1"]
    assert candidate["classification_result"]["final_classification"] == "vus"
    assert any("coverage_quality_adequate" in item for item in candidate["limitations"])


def test_batch_and_annotated_batch_preserve_population_limitations(tmp_path) -> None:
    options = _rate_payload(tmp_path, 105)["options"]
    batch = rate_variant_batch(
        {
            "records": [
                {
                    "gene": "GENE1",
                    "chromosome": "1",
                    "position": 105,
                    "ref": "A",
                    "alt": "G",
                    "disease": "Example disease",
                    "inheritance": "autosomal dominant",
                    "gene_disease_context": _context_input(),
                }
            ],
            "options": options,
        }
    )
    annotated = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "source_version": "annotation-test-v1",
            "input_text": "gene,chromosome,position,ref,alt,consequence\nGENE1,1,105,A,G,missense_variant\n",
            "context": _context_input(),
            "options": options,
        }
    )

    for result in (batch, annotated):
        record = result["results"][0]
        assert record["status"] == "ok"
        assert record["review_note_evidence"][0]["code"] == "BS1"
        assert any("coverage_quality_adequate" in limitation for limitation in record["limitations"])


def test_mcp_query_population_frequency_supports_local_snapshot_and_miss(tmp_path) -> None:
    def call(pos: int) -> dict:
        request = {
            "jsonrpc": "2.0",
            "id": pos,
            "method": "tools/call",
            "params": {
                "name": "query_population_frequency",
                "arguments": {
                    "variant": _variant(pos).model_dump(mode="json"),
                    "data_sources": {
                        "population": {
                            "mode": "local_file",
                            "local_file": str(FIXTURE),
                            "source_version": "gnomad-local-validation-v1",
                            "parser_version": "population-parser-validation-test",
                            "cache_dir": str(tmp_path / f"mcp-cache-{pos}"),
                        }
                    },
                },
            },
        }
        response = asyncio.run(_server().handle_message(json.dumps(request)))
        return json.loads(response["result"]["content"][0]["text"])

    hit = call(100)
    miss = call(999)

    assert hit["population_frequency"]["overall_af"] == 0.0
    assert hit["population_frequency"]["source"]["raw_snapshot_ref"]
    assert miss["population_frequency"]["overall_af"] is None
    assert any("must not be interpreted as absence" in item for item in miss["audit"]["limitations"])


def test_cli_rate_uses_local_population_snapshot_without_network(capsys, tmp_path) -> None:
    exit_code = main(
        [
            "rate",
            "--gene",
            "GENE1",
            "--chromosome",
            "1",
            "--position",
            "102",
            "--ref",
            "A",
            "--alt",
            "G",
            "--disease",
            "Example disease",
            "--inheritance",
            "autosomal dominant",
            "--population-local-file",
            str(FIXTURE),
            "--population-source-version",
            "gnomad-local-validation-v1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["step_results"]["query_population_frequency"]["overall_af"] == 0.06
    assert payload["step_results"]["query_population_frequency"]["source"]["version"] == "gnomad-local-validation-v1"


def test_cache_preserves_provenance_and_source_versions_are_distinct(tmp_path) -> None:
    first = _provider(tmp_path, source_version="gnomad-local-validation-v1").query(_variant(100))
    second = _provider(tmp_path, source_version="gnomad-local-validation-v1").query(_variant(100))
    third = _provider(tmp_path, source_version="gnomad-local-validation-v2").query(_variant(100))

    assert first.source is not None and second.source is not None and third.source is not None
    assert first.source.raw_snapshot_ref == second.source.raw_snapshot_ref
    assert first.source.provenance.query["pos"] == 100
    assert second.source.provenance.source_version == "gnomad-local-validation-v1"
    assert third.source.provenance.source_version == "gnomad-local-validation-v2"
    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cache_files) >= 2
