from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

from config import ServerConfig
from server import McpServer, build_registry

from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient, ProviderHTTPError
from variant_pathogenicity_rater.data_sources.online.ensembl_vep_online import EnsemblVEPOnlineProvider
from variant_pathogenicity_rater.data_sources.online.gnomad_online import GnomADOnlineProvider
from variant_pathogenicity_rater.data_sources.online.literature_online import (
    fetch_online_literature_records,
)
from variant_pathogenicity_rater.data_sources.providers import build_population_provider
from variant_pathogenicity_rater.evidence.clinvar import ClinVarQuery
from variant_pathogenicity_rater.data_sources.providers import ClinVarOnlineProvider
from variant_pathogenicity_rater.literature_agent.schema import LiteratureSearchInput
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.population import generate_population_evidence
from variant_pathogenicity_rater.schemas import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.cli import main


RATE_VARIANT_MODULE = importlib.import_module("variant_pathogenicity_rater.pipeline.rate_variant")


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


class MockGnomADClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def post_json(self, _url: str, _payload: dict) -> dict:
        self.calls += 1
        return self.payload


class MockVEPClient:
    def __init__(self, payload: list | Exception) -> None:
        self.payload = payload
        self.calls = 0

    def get_json(self, _url: str, params: dict | None = None) -> list:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class MockLiteratureClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict | None = None) -> dict:
        self.calls.append(url)
        if url.endswith("esearch.fcgi"):
            return {"esearchresult": {"idlist": ["123456"]}}
        if url.endswith("esummary.fcgi"):
            return {
                "result": {
                    "uids": ["123456"],
                    "123456": {
                        "title": "GENE1 variant PubMed record",
                        "pubdate": "2025",
                        "pubtype": ["Journal Article"],
                    },
                }
            }
        return {"results": [{"pmid": "123456", "title": "GENE1 LitVar record", "abstract": "Abstract only."}]}


def _variant() -> Variant:
    return Variant(
        variant_id="GRCh38-1-21563117-A-C",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=21563117,
        ref="A",
        alt="C",
        gene_symbol="GENE1",
        hgvs_c="NM_000001.1:c.76A>C",
    )


def _online_config(tmp_path: Path, name: str) -> DataSourceConfig:
    return DataSourceConfig(
        name=name,
        mode=ProviderMode.ONLINE,
        online_enabled=True,
        source_version=f"{name}-live-test",
        parser_version=f"{name}-online-parser-test",
        cache_dir=str(tmp_path / name),
    )


def test_default_offline_provider_factory_does_not_call_http() -> None:
    provider = build_population_provider(DataSourceConfig(name="population", mode=ProviderMode.MOCK))
    frequency = provider.query(_variant())
    assert frequency.data_source == "mock_population_frequency"
    assert frequency.source and frequency.source.provenance.cache_hit is None


def test_default_rate_cli_batch_and_mcp_do_not_call_http(monkeypatch, capsys) -> None:
    def fail_http(*_args, **_kwargs):
        raise AssertionError("default offline workflow attempted HTTP")

    monkeypatch.setattr(ProviderHTTPClient, "request", fail_http)

    payload = {
        "gene": "GENE1",
        "chromosome": "1",
        "position": 21563117,
        "ref": "A",
        "alt": "C",
        "disease": "Example disease",
        "options": {"include_clinvar": False, "include_literature": False},
    }
    assert rate_variant(payload)["status"] == "ok"
    assert rate_variant_batch({"records": [payload], "input_format": "json"})["failed"] == 0

    exit_code = main(
        [
            "rate",
            "--gene",
            "GENE1",
            "--chromosome",
            "1",
            "--position",
            "21563117",
            "--ref",
            "A",
            "--alt",
            "C",
            "--disease",
            "Example disease",
        ]
    )
    assert exit_code == 0
    capsys.readouterr()

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "rate_variant", "arguments": payload},
    }
    response = asyncio.run(_server().handle_message(json.dumps(request)))
    assert response["result"]["isError"] is False


def test_online_flags_false_do_not_enable_network_provider(tmp_path: Path) -> None:
    result = rate_variant(
        {
            "gene": "GENE1",
            "chromosome": "1",
            "position": 21563117,
            "ref": "A",
            "alt": "C",
            "disease": "Example disease",
            "options": {"provider_cache_dir": str(tmp_path), "include_clinvar": False, "include_literature": False},
        }
    )
    assert result["status"] == "ok"
    assert result["data_source_modes"]["population"] == "mock"
    assert result["provider_mode_summary"]["population"]["configured_mode"] == "mock"
    assert result["provider_mode_summary"]["population"]["actual_outcome"] == "success"
    assert result["step_results"]["provider_runtime"]["population"]["outcome"] == "success"
    assert result["step_results"]["provider_runtime"]["population"]["configured_mode"] == "mock"
    assert result["providers"]["summary"] == result["provider_mode_summary"]
    assert result["offline_default_mode"] is True


def test_explicit_online_gnomad_flag_uses_mocked_provider_path(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    def post_json(self, _url: str, _payload: dict) -> dict:
        calls["count"] += 1
        return {"data": {"variant": None}}

    monkeypatch.setattr(ProviderHTTPClient, "post_json", post_json)
    result = rate_variant(
        {
            "gene": "GENE1",
            "chromosome": "1",
            "position": 21563117,
            "ref": "A",
            "alt": "C",
            "disease": "Example disease",
            "options": {
                "use_online_gnomad": True,
                "provider_cache_dir": str(tmp_path / "providers"),
                "include_clinvar": False,
                "include_computational": False,
                "include_literature": False,
            },
        }
    )

    assert calls["count"] == 1
    assert result["data_source_modes"]["population"] == "online"
    assert result["step_results"]["query_population_frequency"]["source"]["provenance"]["cache_hit"] is False
    assert result["step_results"]["query_population_frequency"]["source"]["version"] == "gnomAD gnomad_r4 live GraphQL"
    assert result["provider_mode_summary"]["population"]["actual_outcome"] == "no_record"
    assert result["provider_mode_summary"]["population"]["outcome"] == "no_record"
    assert result["step_results"]["provider_runtime"]["population"]["outcome"] == "no_record"
    assert result["provider_mode_summary"]["population"]["raw_record_hash"] == result["provider_mode_summary"]["population"]["raw_hash"]
    assert result["provider_mode_summary"]["population"]["query"]["variant_id"] == "1-21563117-A-C"
    assert not any(item["code"] == "PM2" for item in result["applied_evidence"])


def test_mcp_online_gnomad_flag_reports_provider_summary(monkeypatch, tmp_path: Path) -> None:
    def post_json(_self, _url: str, payload: dict) -> dict:
        assert payload["variables"]["variantId"] == "1-21563117-A-C"
        return {"data": {"variant": None}}

    monkeypatch.setattr(ProviderHTTPClient, "post_json", post_json)
    request = {
        "jsonrpc": "2.0",
        "id": 76,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": {
                "gene": "GENE1",
                "chromosome": "1",
                "position": 21563117,
                "ref": "A",
                "alt": "C",
                "disease": "Example disease",
                "options": {
                    "use_online_gnomad": True,
                    "provider_cache_dir": str(tmp_path / "providers"),
                    "include_clinvar": False,
                    "include_computational": False,
                    "include_literature": False,
                },
            },
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    payload = json.loads(response["result"]["content"][0]["text"])

    assert response["result"]["isError"] is False
    assert payload["data_source_modes"]["population"] == "online"
    assert payload["provider_mode_summary"]["population"]["actual_outcome"] == "no_record"
    assert payload["provider_mode_summary"]["population"]["query"]["variant_id"] == "1-21563117-A-C"


def test_online_vep_failure_is_provider_summary_failure(monkeypatch, tmp_path: Path) -> None:
    def get_json(_self, _url: str, params: dict | None = None) -> list:
        raise ProviderHTTPError("Provider HTTP error 503", url="https://rest.ensembl.org", status=503)

    monkeypatch.setattr(ProviderHTTPClient, "get_json", get_json)
    result = rate_variant(
        {
            "gene": "GENE1",
            "chromosome": "1",
            "position": 21563117,
            "ref": "A",
            "alt": "C",
            "disease": "Example disease",
            "options": {
                "use_online_vep": True,
                "provider_cache_dir": str(tmp_path / "providers"),
                "include_clinvar": False,
                "include_literature": False,
            },
        }
    )

    computational = result["provider_mode_summary"]["computational"]
    assert computational["requested_mode"] == "online"
    assert computational["configured_mode"] == "online"
    assert computational["actual_outcome"] == "failure"
    assert computational["outcome"] == "failure"
    assert computational["error_type"] == "Ensembl_VEP_online_query"
    assert result["step_results"]["provider_runtime"]["computational"]["outcome"] == "failure"
    assert computational["source_version"] == "Ensembl REST VEP live"
    assert computational["endpoint"] == "https://rest.ensembl.org/vep/homo_sapiens/region"
    assert computational["query"]["variant_id"] == "GRCh38-1-21563117-A-C"
    assert result["unresolved_placeholder_mode"] is True
    assert not any(item["code"] in {"PP3", "BP4"} for item in result["applied_evidence"])


def test_gnomad_mocked_graphql_maps_population_frequency_and_cache(tmp_path: Path) -> None:
    client = MockGnomADClient(
        {
            "data": {
                "variant": {
                    "variantId": "1-21563117-A-C",
                    "genome": {"ac": 2, "an": 1000, "af": 0.002, "homozygote_count": 0},
                    "populations": [
                        {"id": "afr", "ac": 1, "an": 100, "af": 0.01, "homozygote_count": 0}
                    ],
                    "faf95": [{"population": "afr", "faf95": 0.012}],
                }
            }
        }
    )
    provider = GnomADOnlineProvider(_online_config(tmp_path, "population"), http_client=client)

    first = provider.query(_variant())
    second = provider.query(_variant())

    assert client.calls == 1
    assert first.allele_count == 2
    assert first.allele_number == 1000
    assert first.overall_af == 0.002
    assert first.max_pop_af == 0.01
    assert first.faf95 == 0.012
    assert second.source and second.source.provenance.cache_hit is True


def test_gnomad_no_record_found_does_not_infer_pm2(tmp_path: Path) -> None:
    provider = GnomADOnlineProvider(_online_config(tmp_path, "population"), http_client=MockGnomADClient({"data": {"variant": None}}))
    frequency = provider.query(_variant())
    items, decision = generate_population_evidence(
        variant=_variant(),
        context=GeneDiseaseContext(
            gene="GENE1",
            disease="Example disease",
            inheritance="autosomal dominant",
            disease_prevalence=0.0001,
            population_ancestry="global",
        ),
        frequency=frequency,
        thresholds=PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert items == []
    assert decision.recommended_code is None
    assert any("not evidence of population absence" in item for item in frequency.limitations)


def test_vep_mocked_rest_maps_predictors_and_transcript_context(tmp_path: Path) -> None:
    provider = EnsemblVEPOnlineProvider(
        _online_config(tmp_path, "computational"),
        http_client=MockVEPClient(
            [
                {
                    "most_severe_consequence": "missense_variant",
                    "transcript_consequences": [
                        {
                            "transcript_id": "ENST000001",
                            "hgvsp": "ENSP000001:p.Lys26Arg",
                            "cadd_phred": 25.0,
                            "revel_score": 0.82,
                            "sift_prediction": "deleterious",
                            "polyphen_prediction": "probably_damaging",
                        }
                    ],
                }
            ]
        ),
    )

    predictions = provider.query(_variant())

    methods = {prediction.method for prediction in predictions}
    assert {"CADD", "REVEL", "SIFT", "PolyPhen"}.issubset(methods)
    assert all(prediction.source.provenance.raw_record_hash for prediction in predictions)
    assert all(prediction.transcript == "ENST000001" for prediction in predictions)
    assert any("MutationTaster" in item for prediction in predictions for item in prediction.limitations)


def test_vep_timeout_failure_becomes_limitation(tmp_path: Path) -> None:
    provider = EnsemblVEPOnlineProvider(
        _online_config(tmp_path, "computational"),
        http_client=MockVEPClient(
            ProviderHTTPError("Provider HTTP error 400", url="https://rest.ensembl.org", status=400)
        ),
    )
    predictions = provider.query(_variant())

    assert predictions
    assert predictions[0].candidate_only is True
    assert any("query failed" in item for item in predictions[0].limitations)
    assert predictions[0].source.provenance.cache_hit is False


def test_pubmed_litvar_mocked_eutils_maps_literature_records(tmp_path: Path) -> None:
    records, limitations = fetch_online_literature_records(
        LiteratureSearchInput(
            gene="GENE1",
            variant="NM_000001.1:c.76A>C",
            disease="GENE1 disorder",
            use_online_pubmed=True,
            use_online_litvar=True,
            provider_cache_dir=str(tmp_path / "lit-cache"),
        ),
        config=_online_config(tmp_path, "literature"),
        http_client=MockLiteratureClient(),
    )

    assert {record.source for record in records} == {"PubMed", "LitVar"}
    assert all(record.provenance["raw_record_hash"] for record in records)
    assert any("abstract-only" in item for record in records for item in record.provenance.get("limitations", []))
    assert all("no literature evidence is applied" in " ".join(limitations).lower() for _ in [0])


def test_rate_variant_online_literature_summary_is_candidate_only(monkeypatch, tmp_path: Path) -> None:
    def fake_literature(payload: dict):
        from variant_pathogenicity_rater.literature_agent.schema import LiteratureSearchResult

        assert payload["use_online_pubmed"] is True
        return LiteratureSearchResult(
            literature_search_results=[],
            limitations=["PubMed mocked online record stayed candidate-only."],
            suggested_evidence=[
                {
                    "code": "PS3",
                    "candidate_only": True,
                    "applied": False,
                    "suggested_strength": "supporting",
                }
            ],
            evidence_items=[
                {
                    "code": "PS3",
                    "strength": "none",
                    "candidate_only": True,
                    "applied": False,
                }
            ],
            reviewed_evidence_drafts=[{"evidence_status": "needs_more_info"}],
            provenance={
                "online_pubmed_requested": True,
                "query": {"gene": payload["gene"], "variant": payload["variant"]},
                "source_version": "PubMed/LitVar live",
            },
            applied_evidence=[],
            final_classification_changed=False,
        )

    monkeypatch.setattr(RATE_VARIANT_MODULE, "search_and_summarize_literature", fake_literature)
    result = rate_variant(
        {
            "gene": "GENE1",
            "chromosome": "1",
            "position": 21563117,
            "ref": "A",
            "alt": "C",
            "disease": "Example disease",
            "options": {
                "use_online_pubmed": True,
                "provider_cache_dir": str(tmp_path / "providers"),
                "include_clinvar": False,
                "include_population": False,
                "include_computational": False,
            },
        }
    )

    assert result["data_source_modes"]["literature"] == "online"
    literature_step = result["step_results"]["search_and_summarize_literature"]
    assert literature_step["applied_evidence"] == []
    assert literature_step["final_classification_changed"] is False
    assert all(item["applied"] is False for item in literature_step["evidence_items"])
    assert not any(item["code"] == "PS3" for item in result["applied_evidence"])


def test_clinvar_online_provenance_and_no_pp5_bp6_applied(tmp_path: Path) -> None:
    def http_get(_endpoint: str, _params: dict) -> dict:
        return {
            "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            "result": {
                "uids": ["123"],
                "123": {
                    "uid": "123",
                    "title": "Pathogenic GENE1 variant",
                    "clinical_significance": {"description": "Pathogenic", "review_status": "reviewed by expert panel"},
                    "trait_name": "GENE1 disorder",
                    "germline_classification": {"description": "Pathogenic"},
                },
            },
        }

    provider = ClinVarOnlineProvider(_online_config(tmp_path, "clinvar"), http_get=http_get)
    result = provider.query(ClinVarQuery(variation_id="123", condition="GENE1 disorder"))

    assert result.records
    assert result.records[0].source.provenance.cache_hit is False
    assert result.candidate_evidence_items
    assert all(item.applied is False for item in result.candidate_evidence_items)
    assert all(item.strength == "none" for item in result.candidate_evidence_items)


def test_alpl_online_provider_flow_with_slash_clinvar_date_is_review_gated(
    monkeypatch, tmp_path: Path
) -> None:
    calls: dict[str, Any] = {"gnomad_payloads": [], "vep_urls": [], "clinvar": 0}

    def clinvar_http_get(_self, endpoint: str, params: dict[str, str]) -> dict:
        calls["clinvar"] += 1
        if endpoint.endswith("esearch.fcgi"):
            assert "ALPL[gene]" in params["term"]
            assert "NM_000478.6:c.305A>C" in params["term"]
            return {"esearchresult": {"idlist": ["305"]}}
        return {
            "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            "result": {
                "uids": ["305"],
                "305": {
                    "uid": "305",
                    "variation_id": "305",
                    "clinical_significance": {
                        "description": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "last_evaluated": "2025/08/29",
                    },
                    "trait_set": [{"trait_name": "Hypophosphatasia"}],
                    "classification_type": "germline",
                    "number_submitters": 6,
                },
            },
        }

    def post_json(_self, url: str, payload: dict) -> dict:
        calls["gnomad_payloads"].append(payload)
        assert "gnomad" in url.lower()
        assert payload["variables"]["variantId"] == "1-21563117-A-C"
        return {"data": {"variant": None}}

    def get_json(_self, url: str, params: dict | None = None) -> list:
        calls["vep_urls"].append(url)
        assert "1:21563117-21563117:1/A/C" in url
        return [
            {
                "most_severe_consequence": "missense_variant",
                "transcript_consequences": [
                    {
                        "transcript_id": "NM_000478.6",
                        "hgvsp": "NP_000469.3:p.Thr102Pro",
                    }
                ],
            }
        ]

    def fake_literature(payload: dict):
        from variant_pathogenicity_rater.literature_agent.schema import LiteratureSearchResult

        assert payload["use_online_pubmed"] is True
        assert payload["gene"] == "ALPL"
        assert payload["variant"] == "NM_000478.6:c.305A>C"
        return LiteratureSearchResult(
            literature_search_results=[],
            limitations=["PubMed mocked online record stayed candidate-only."],
            suggested_evidence=[
                {"code": "PS3", "candidate_only": True, "applied": False, "suggested_strength": "supporting"}
            ],
            evidence_items=[{"code": "PS3", "strength": "none", "candidate_only": True, "applied": False}],
            reviewed_evidence_drafts=[{"evidence_status": "needs_more_info"}],
            provenance={
                "online_pubmed_requested": True,
                "query": {"gene": payload["gene"], "variant": payload["variant"]},
                "source_version": "PubMed/LitVar live",
            },
            applied_evidence=[],
            final_classification_changed=False,
        )

    monkeypatch.setattr(ClinVarOnlineProvider, "_http_get", clinvar_http_get)
    monkeypatch.setattr(ProviderHTTPClient, "post_json", post_json)
    monkeypatch.setattr(ProviderHTTPClient, "get_json", get_json)
    monkeypatch.setattr(RATE_VARIANT_MODULE, "search_and_summarize_literature", fake_literature)

    result = rate_variant(
        {
            "gene": "ALPL",
            "transcript": "NM_000478.6",
            "hgvs_c": "NM_000478.6:c.305A>C",
            "chromosome": "1",
            "position": 21563117,
            "ref": "A",
            "alt": "C",
            "genome_build": "GRCh38",
            "disease": "Hypophosphatasia",
            "inheritance": "autosomal_dominant",
            "options": {
                "use_online_clinvar": True,
                "use_online_gnomad": True,
                "use_online_vep": True,
                "use_online_pubmed": True,
                "provider_cache_dir": str(tmp_path / "providers"),
            },
        }
    )

    assert result["status"] == "ok"
    assert result["data_source_modes"]["clinvar"] == "online"
    assert result["data_source_modes"]["population"] == "online"
    assert result["data_source_modes"]["computational"] == "online"
    assert result["data_source_modes"]["literature"] == "online"
    assert result["data_source_modes_semantics"].startswith("Configured/requested")
    assert result["offline_default_mode"] is True
    assert result["mock_mode"] is True
    assert result["unresolved_placeholder_mode"] is True
    provider_summary = result["provider_mode_summary"]
    assert set(provider_summary) >= {"clinvar", "population", "computational", "literature", "clingen_erepo"}
    assert provider_summary["clinvar"]["requested_mode"] == "online"
    assert provider_summary["clinvar"]["configured_mode"] == "online"
    assert provider_summary["clinvar"]["actual_outcome"] == "success"
    assert provider_summary["clinvar"]["outcome"] == "success"
    assert provider_summary["clinvar"]["source_version"] == "NCBI ClinVar E-utilities live"
    assert provider_summary["population"]["actual_outcome"] == "no_record"
    assert provider_summary["population"]["outcome"] == "no_record"
    assert provider_summary["population"]["query"]["variant_id"] == "1-21563117-A-C"
    assert provider_summary["population"]["source_version"] == "gnomAD gnomad_r4 live GraphQL"
    assert provider_summary["computational"]["actual_outcome"] == "success"
    assert provider_summary["computational"]["outcome"] == "success"
    assert provider_summary["computational"]["source_version"] == "Ensembl REST VEP live"
    assert provider_summary["computational"]["query"]["variant_id"] == "GRCh38-1-21563117-A-C"
    assert provider_summary["literature"]["requested_mode"] == "online"
    assert provider_summary["literature"]["actual_outcome"] == "no_record"
    assert provider_summary["literature"]["outcome"] == "no_record"
    provider_runtime = result["step_results"]["provider_runtime"]
    assert provider_runtime["clinvar"]["outcome"] == "success"
    assert provider_runtime["population"]["outcome"] == "no_record"
    assert provider_runtime["computational"]["outcome"] == "success"
    assert provider_runtime["literature"]["outcome"] == "no_record"
    assert result["providers"]["summary"] == provider_summary
    assert calls["clinvar"] == 2
    assert calls["gnomad_payloads"]
    assert calls["vep_urls"]
    assert "Invalid isoformat" not in " ".join(result["limitations"])

    clinvar_step = result["step_results"]["query_clinvar"]
    assert clinvar_step["records"]
    clinvar_record = clinvar_step["records"][0]
    provenance = clinvar_record["source"]["provenance"]
    assert clinvar_record["last_evaluated"] == "2025-08-29"
    assert provenance["raw_last_evaluated"] == "2025/08/29"
    assert provenance["last_evaluated_precision"] == "day"
    for field in {
        "provider_mode",
        "cache_hit",
        "query",
        "source_version",
        "endpoint",
        "request_url",
        "parser_version",
        "raw_record_hash",
        "retrieved_at",
    }:
        assert provenance[field] is not None

    assert clinvar_step["candidate_evidence_items"]
    assert all(item["applied"] is False for item in clinvar_step["candidate_evidence_items"])
    assert all(item["strength"] == "none" for item in clinvar_step["candidate_evidence_items"])
    assert not any(item["code"] in {"PP5", "BP6"} for item in result["applied_evidence"])

    population_step = result["step_results"]["query_population_frequency"]
    assert population_step["source"]["provenance"]["query"]["variant_id"] == "1-21563117-A-C"
    assert population_step["source"]["version"] == "gnomAD gnomad_r4 live GraphQL"
    assert population_step["is_absent"] is False
    assert not any(item["code"] == "PM2" for item in result["applied_evidence"])

    assert result["normalized_variant"]["chrom"] == "1"
    assert result["normalized_variant"]["pos"] == 21563117
    assert result["variant_resolution"]["resolved_coordinate"]["chrom"] == "1"
    assert result["variant_resolution"]["resolved_coordinate"]["pos"] == 21563117
    assert result["variant_resolution"]["resolved_coordinate"]["provenance"][0]["source"] == "normalized_variant"
    assert result["variant_resolution"]["resolved_hgvs_p"]["hgvs_p"] == "NP_000469.3:p.Thr102Pro"
    assert result["variant_resolution"]["resolved_hgvs_p"]["consequence"] == "missense_variant"
    assert result["variant_resolution"]["resolved_hgvs_p"]["provenance"][0]["source"] == "computational"
    assert result["resolved_variant"]["hgvs_p"] == "NP_000469.3:p.Thr102Pro"

    computational_step = result["step_results"]["evaluate_computational_evidence"]
    predictor_calls = computational_step["summary"]["predictor_calls"]
    assert predictor_calls
    assert any(
        "supported predictor field" in limitation
        for call in predictor_calls
        for limitation in call["limitations"]
    )
    literature_step = result["step_results"]["search_and_summarize_literature"]
    assert literature_step["provenance"]["query"]["variant"] == "NM_000478.6:c.305A>C"
    assert literature_step["applied_evidence"] == []
    assert literature_step["final_classification_changed"] is False


def test_cli_provider_cache_dir_flag_without_online_keeps_offline_default(capsys, tmp_path: Path) -> None:
    exit_code = main(
        [
            "rate",
            "--gene",
            "GENE1",
            "--chromosome",
            "1",
            "--position",
            "21563117",
            "--ref",
            "A",
            "--alt",
            "C",
            "--disease",
            "Example disease",
            "--provider-cache-dir",
            str(tmp_path / "providers"),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"population": "mock"' in captured.out


def test_cli_online_pubmed_reports_literature_data_source_mode(monkeypatch, capsys, tmp_path: Path) -> None:
    def fake_literature(_payload: dict):
        from variant_pathogenicity_rater.literature_agent.schema import LiteratureSearchResult

        return LiteratureSearchResult(
            limitations=["mocked PubMed candidate-only path"],
            applied_evidence=[],
            final_classification_changed=False,
        )

    monkeypatch.setattr(RATE_VARIANT_MODULE, "search_and_summarize_literature", fake_literature)
    exit_code = main(
        [
            "rate",
            "--gene",
            "GENE1",
            "--chromosome",
            "1",
            "--position",
            "21563117",
            "--ref",
            "A",
            "--alt",
            "C",
            "--disease",
            "Example disease",
            "--online-pubmed",
            "--provider-cache-dir",
            str(tmp_path / "providers"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data_source_modes"]["literature"] == "online"
    assert payload["provider_mode_summary"]["literature"]["requested_mode"] == "online"
    assert payload["provider_mode_summary"]["literature"]["configured_mode"] == "online"


@pytest.mark.online_gnomad_smoke
def test_optional_live_gnomad_smoke_is_env_gated(tmp_path: Path) -> None:
    if (
        os.environ.get("VPR_RUN_LIVE_PROVIDER_SMOKE") != "1"
        or os.environ.get("VPR_GNOMAD_MODE") != "online"
        or os.environ.get("VPR_GNOMAD_ONLINE_ENABLED") != "true"
    ):
        pytest.skip("gnomAD online smoke is opt-in and requires explicit env gates.")
    provider = GnomADOnlineProvider(_online_config(tmp_path, "population"))
    assert provider.query(_variant()).source is not None
