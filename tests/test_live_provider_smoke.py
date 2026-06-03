from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

from config import ServerConfig
from server import McpServer, build_registry

from variant_pathogenicity_rater.cli import main
from variant_pathogenicity_rater.config.thresholds import PopulationRuleThresholds
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient, ProviderHTTPError
from variant_pathogenicity_rater.data_sources.online.ensembl_vep_online import (
    EnsemblVEPOnlineProvider,
)
from variant_pathogenicity_rater.data_sources.online.gnomad_online import GnomADOnlineProvider
from variant_pathogenicity_rater.data_sources.online.literature_online import (
    fetch_online_literature_records,
)
from variant_pathogenicity_rater.data_sources.providers import ClinVarOnlineProvider
from variant_pathogenicity_rater.evidence.clinvar import ClinVarQuery
from variant_pathogenicity_rater.literature_agent.schema import LiteratureSearchInput
from variant_pathogenicity_rater.population import generate_population_evidence
from variant_pathogenicity_rater.schemas import GeneDiseaseContext, Variant

def _live_smoke_enabled() -> bool:
    return os.environ.get("VPR_RUN_LIVE_PROVIDER_SMOKE") == "1"


def _skip_unless_live_smoke() -> None:
    if not _live_smoke_enabled():
        pytest.skip("Live provider smoke is opt-in; set VPR_RUN_LIVE_PROVIDER_SMOKE=1.")


def _cache_root(tmp_path: Path) -> Path:
    configured = os.environ.get("VPR_LIVE_PROVIDER_CACHE_DIR")
    return Path(configured) if configured else tmp_path / "live-provider-cache"


def _timeout() -> float:
    return float(os.environ.get("VPR_LIVE_PROVIDER_TIMEOUT", "10"))


def _online_config(
    tmp_path: Path,
    *,
    name: str,
    cache_name: str,
    parser_version: str,
    source_version: str,
) -> DataSourceConfig:
    return DataSourceConfig(
        name=name,
        mode=ProviderMode.ONLINE,
        online_enabled=True,
        source_version=source_version,
        parser_version=parser_version,
        cache_dir=str(_cache_root(tmp_path) / cache_name),
        timeout_seconds=_timeout(),
        email=os.environ.get("VPR_LIVE_PROVIDER_EMAIL"),
        user_agent=os.environ.get("VPR_LIVE_PROVIDER_USER_AGENT"),
    )


def _assert_provenance(
    provenance: Any,
    *,
    expected_source: str,
    expected_cache_hit: bool | None,
) -> None:
    payload = _as_mapping(provenance)
    assert payload.get("data_source") == expected_source
    assert payload.get("source_version")
    assert payload.get("query")
    assert payload.get("retrieved_at")
    assert payload.get("raw_record_hash")
    assert payload.get("parser_version")
    assert payload.get("provider_mode") in {"online", "ProviderMode.ONLINE"}
    assert payload.get("endpoint") or payload.get("source_url") or payload.get("request_url")
    assert payload.get("cache_hit") is expected_cache_hit


def _assert_no_codes(items: Iterable[Any], forbidden_codes: set[str]) -> None:
    observed = {_code(item) for item in items}
    assert forbidden_codes.isdisjoint(observed)


def _assert_candidate_only_items(items: Iterable[Any]) -> None:
    for item in items:
        payload = _as_mapping(item)
        assert payload.get("applied") is False
        assert payload.get("strength") == "none"
        assert payload.get("candidate_only") is True


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return dict(value)


def _code(item: Any) -> str | None:
    payload = _as_mapping(item)
    code = payload.get("code")
    return str(getattr(code, "value", code)) if code is not None else None


def _alpl_variant() -> Variant:
    return Variant(
        variant_id="GRCh38-1-21563117-A-C",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=21563117,
        ref="A",
        alt="C",
        gene_symbol="ALPL",
        hgvs_c="NM_000478.6:c.305A>C",
    )


def _alpl_context() -> GeneDiseaseContext:
    return GeneDiseaseContext(
        gene_symbol="ALPL",
        disease_name="Hypophosphatasia",
        inheritance_mode="autosomal dominant",
        disease_prevalence=0.0001,
        population_ancestry="global",
    )


def _server() -> McpServer:
    config = ServerConfig(
        server_name="variant-pathogenicity-rater-live-smoke-test",
        server_version="0.1.0",
        log_level="ERROR",
        tools_package="tools",
        enable_health_tool=True,
        environment="test",
    )
    return McpServer(config, build_registry(config))


class CountingGnomADClient:
    def __init__(self, payload: dict[str, Any] | Exception) -> None:
        self.payload = payload
        self.calls = 0

    def post_json(self, _url: str, _payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class CountingVEPClient:
    def __init__(self, payload: list[dict[str, Any]] | Exception) -> None:
        self.payload = payload
        self.calls = 0

    def get_json(self, _url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class CountingLiteratureClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(url)
        if self.fail:
            raise ProviderHTTPError("literature timeout", url=url)
        if url.endswith("esummary.fcgi"):
            return {
                "result": {
                    "uids": ["36361766"],
                    "36361766": {
                        "title": "ALPL c.305A>C PubMed smoke record",
                        "pubdate": "2022",
                        "pubtype": ["Journal Article"],
                    },
                }
            }
        if url.endswith("variant/search"):
            return {
                "results": [
                    {
                        "pmid": "36361766",
                        "title": "ALPL c.305A>C LitVar smoke record",
                        "abstract": "Abstract only.",
                    }
                ]
            }
        return {"esearchresult": {"idlist": ["36361766"]}}


def test_live_smoke_helper_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VPR_RUN_LIVE_PROVIDER_SMOKE", raising=False)
    assert _live_smoke_enabled() is False


def test_mocked_clinvar_cache_and_candidate_only_boundary(tmp_path: Path) -> None:
    calls = {"count": 0}

    def http_get(_endpoint: str, _params: dict[str, str]) -> dict[str, Any]:
        calls["count"] += 1
        return {
            "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            "result": {
                "uids": ["123"],
                "123": {
                    "uid": "123",
                    "title": "Pathogenic ALPL variant",
                    "clinical_significance": {
                        "description": "Pathogenic",
                        "review_status": "criteria provided, reviewed by expert panel",
                    },
                    "trait_name": "Hypophosphatasia",
                    "germline_classification": {"description": "Pathogenic"},
                },
            },
        }

    provider = ClinVarOnlineProvider(
        _online_config(
            tmp_path,
            name="clinvar",
            cache_name="clinvar",
            parser_version="clinvar-live-smoke-parser",
            source_version="NCBI ClinVar E-utilities live",
        ),
        http_get=http_get,
    )

    first = provider.query(ClinVarQuery(variation_id="123", condition="Hypophosphatasia"))
    second = provider.query(ClinVarQuery(variation_id="123", condition="Hypophosphatasia"))

    assert calls["count"] == 1
    assert first.records
    assert second.records
    _assert_provenance(first.records[0].source.provenance, expected_source="ClinVar", expected_cache_hit=False)
    _assert_provenance(second.records[0].source.provenance, expected_source="ClinVar", expected_cache_hit=True)
    _assert_candidate_only_items(first.candidate_evidence_items)


def test_mocked_gnomad_cache_no_record_and_failure_are_limitations(tmp_path: Path) -> None:
    provider = GnomADOnlineProvider(
        _online_config(
            tmp_path,
            name="population",
            cache_name="gnomad",
            parser_version="gnomad-live-smoke-parser",
            source_version="gnomAD gnomad_r4 live GraphQL",
        ),
        http_client=CountingGnomADClient({"data": {"variant": None}}),
    )

    first = provider.query(_alpl_variant())
    second = provider.query(_alpl_variant())
    items, decision = generate_population_evidence(
        variant=_alpl_variant(),
        context=_alpl_context(),
        frequency=first,
        thresholds=PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )

    assert first.is_absent is False
    assert first.limitations
    assert items == []
    assert decision.recommended_code is None
    _assert_provenance(first.source.provenance, expected_source="population", expected_cache_hit=False)
    _assert_provenance(second.source.provenance, expected_source="population", expected_cache_hit=True)

    failed = GnomADOnlineProvider(
        _online_config(
            tmp_path,
            name="population",
            cache_name="gnomad-failure",
            parser_version="gnomad-live-smoke-parser",
            source_version="gnomAD gnomad_r4 live GraphQL",
        ),
        http_client=CountingGnomADClient(ProviderHTTPError("gnomAD timeout")),
    ).query(_alpl_variant())
    assert failed.limitations
    assert any("query failed" in item for item in failed.limitations)


def test_mocked_vep_cache_missing_predictors_and_failure_are_limitations(tmp_path: Path) -> None:
    client = CountingVEPClient(
        [
            {
                "most_severe_consequence": "missense_variant",
                "transcript_consequences": [
                    {
                        "transcript_id": "ENST00000374840",
                        "hgvsp": "ENSP00000363973:p.Thr102Pro",
                    }
                ],
            }
        ]
    )
    provider = EnsemblVEPOnlineProvider(
        _online_config(
            tmp_path,
            name="computational",
            cache_name="vep",
            parser_version="vep-live-smoke-parser",
            source_version="Ensembl REST VEP live",
        ),
        http_client=client,
    )

    first = provider.query(_alpl_variant())
    second = provider.query(_alpl_variant())

    assert client.calls == 1
    assert first
    assert second
    assert all(item.source.provenance.cache_hit is False for item in first)
    assert all(item.source.provenance.cache_hit is True for item in second)
    assert any("supported predictor field" in limitation for item in first for limitation in item.limitations)

    failed = EnsemblVEPOnlineProvider(
        _online_config(
            tmp_path,
            name="computational",
            cache_name="vep-failure",
            parser_version="vep-live-smoke-parser",
            source_version="Ensembl REST VEP live",
        ),
        http_client=CountingVEPClient(ProviderHTTPError("VEP timeout")),
    ).query(_alpl_variant())
    assert failed
    assert failed[0].candidate_only is True
    assert any("query failed" in item for item in failed[0].limitations)


def test_mocked_pubmed_litvar_cache_and_failure_are_candidate_only(tmp_path: Path) -> None:
    config = _online_config(
        tmp_path,
        name="literature",
        cache_name="literature",
        parser_version="literature-live-smoke-parser",
        source_version="PubMed/LitVar live",
    )
    request = LiteratureSearchInput(
        gene="ALPL",
        variant="NM_000478.6:c.305A>C",
        disease="Hypophosphatasia",
        pmids=["36361766"],
        use_online_pubmed=True,
        use_online_litvar=True,
    )
    client = CountingLiteratureClient()

    first, first_limitations = fetch_online_literature_records(request, config=config, http_client=client)
    second, second_limitations = fetch_online_literature_records(request, config=config, http_client=client)

    assert client.calls == [
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        "https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/search",
    ]
    assert {record.source for record in first} == {"PubMed", "LitVar"}
    assert {record.provenance["cache_hit"] for record in first} == {False}
    assert {record.provenance["cache_hit"] for record in second} == {True}
    assert all(record.provenance["candidate_only"] is True for record in first)
    assert all(record.provenance["applied"] is False for record in first)
    assert "no literature evidence is applied" in " ".join(first_limitations + second_limitations).lower()

    failed, failed_limitations = fetch_online_literature_records(
        request,
        config=_online_config(
            tmp_path,
            name="literature",
            cache_name="literature-failure",
            parser_version="literature-live-smoke-parser",
            source_version="PubMed/LitVar live",
        ),
        http_client=CountingLiteratureClient(fail=True),
    )
    assert failed == []
    assert any("query failed" in item or "failure" in item.lower() for item in failed_limitations)


def test_mcp_rate_variant_schema_still_exposes_online_provider_options() -> None:
    schema = {tool["name"]: tool["inputSchema"] for tool in _server().list_tools()["tools"]}[
        "rate_variant"
    ]
    options = schema["properties"]["options"]
    for field in {
        "use_online_clinvar",
        "use_online_gnomad",
        "use_online_vep",
        "use_online_pubmed",
        "use_online_litvar",
        "provider_cache_dir",
    }:
        assert field in options["properties"]


@pytest.mark.online_clinvar_smoke
def test_live_clinvar_eutils_smoke(tmp_path: Path) -> None:
    _skip_unless_live_smoke()
    provider = ClinVarOnlineProvider(
        _online_config(
            tmp_path,
            name="clinvar",
            cache_name="clinvar-live",
            parser_version="clinvar-live-smoke-parser",
            source_version="NCBI ClinVar E-utilities live",
        )
    )

    result = provider.query(
        ClinVarQuery(
            gene="ALPL",
            hgvs_c="NM_000478.6:c.305A>C",
            condition="Hypophosphatasia",
        )
    )

    if not result.records:
        assert result.limitations
        return
    record = result.records[0]
    assert record.source
    assert record.clinical_significance
    assert record.review_status or record.review_confidence is not None
    _assert_provenance(record.source.provenance, expected_source="ClinVar", expected_cache_hit=False)
    _assert_candidate_only_items(result.candidate_evidence_items)


@pytest.mark.online_gnomad_smoke
def test_live_gnomad_graphql_smoke(tmp_path: Path) -> None:
    _skip_unless_live_smoke()
    provider = GnomADOnlineProvider(
        _online_config(
            tmp_path,
            name="population",
            cache_name="gnomad-live",
            parser_version="gnomad-live-smoke-parser",
            source_version="gnomAD gnomad_r4 live GraphQL",
        )
    )

    frequency = provider.query(_alpl_variant())
    _assert_provenance(frequency.source.provenance, expected_source="population", expected_cache_hit=False)
    assert frequency.is_absent is False
    assert frequency.allele_count is not None or frequency.allele_number is not None or frequency.limitations
    items, decision = generate_population_evidence(
        variant=_alpl_variant(),
        context=_alpl_context(),
        frequency=frequency,
        thresholds=PopulationRuleThresholds(disease_specific=True, penetrance_provided=True),
    )
    if frequency.allele_count is None and frequency.allele_number is None:
        assert items == []
        assert decision.recommended_code is None


@pytest.mark.online_vep_smoke
def test_live_ensembl_vep_rest_smoke(tmp_path: Path) -> None:
    _skip_unless_live_smoke()
    provider = EnsemblVEPOnlineProvider(
        _online_config(
            tmp_path,
            name="computational",
            cache_name="vep-live",
            parser_version="vep-live-smoke-parser",
            source_version="Ensembl REST VEP live",
        )
    )

    predictions = provider.query(_alpl_variant())
    assert predictions
    _assert_provenance(
        predictions[0].source.provenance,
        expected_source="computational",
        expected_cache_hit=False,
    )
    assert any(
        prediction.transcript
        or prediction.hgvs_p
        or "missense" in prediction.prediction
        or prediction.limitations
        for prediction in predictions
    )


@pytest.mark.online_literature_smoke
def test_live_pubmed_eutils_smoke(tmp_path: Path) -> None:
    _skip_unless_live_smoke()
    records, limitations = fetch_online_literature_records(
        LiteratureSearchInput(
            gene="ALPL",
            variant="NM_000478.6:c.305A>C",
            disease="Hypophosphatasia",
            pmids=["36361766"],
            use_online_pubmed=True,
        ),
        config=_online_config(
            tmp_path,
            name="literature",
            cache_name="pubmed-live",
            parser_version="literature-live-smoke-parser",
            source_version="PubMed EUtils live",
        ),
    )

    if not records:
        assert limitations
        return
    record = records[0]
    assert record.pmid == "36361766"
    assert record.title
    assert record.source == "PubMed"
    assert record.retrieval_timestamp
    assert record.provenance["candidate_only"] is True
    assert record.provenance["applied"] is False
    assert record.provenance["cache_hit"] is False
    assert record.provenance["raw_record_hash"]


@pytest.mark.online_literature_smoke
def test_live_litvar_optional_experimental_smoke(tmp_path: Path) -> None:
    _skip_unless_live_smoke()
    if os.environ.get("VPR_RUN_LIVE_LITVAR_SMOKE") != "1":
        pytest.skip("LitVar live smoke is optional/experimental; set VPR_RUN_LIVE_LITVAR_SMOKE=1.")
    records, limitations = fetch_online_literature_records(
        LiteratureSearchInput(
            gene="ALPL",
            variant="NM_000478.6:c.305A>C",
            disease="Hypophosphatasia",
            variant_aliases=["1-21563117-A-C"],
            use_online_litvar=True,
        ),
        config=_online_config(
            tmp_path,
            name="literature",
            cache_name="litvar-live",
            parser_version="literature-live-smoke-parser",
            source_version="LitVar live experimental",
        ),
    )

    if not records:
        assert limitations
        return
    record = records[0]
    assert record.source == "LitVar"
    assert record.title
    assert record.provenance["candidate_only"] is True
    assert record.provenance["applied"] is False
    assert record.provenance["raw_record_hash"]


@pytest.mark.online_clinvar_smoke
@pytest.mark.online_gnomad_smoke
@pytest.mark.online_vep_smoke
@pytest.mark.online_literature_smoke
def test_live_cli_rate_and_literature_smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _skip_unless_live_smoke()
    cache_dir = str(_cache_root(tmp_path) / "cli")

    for provider_flag, expected_mode in [
        ("--online-clinvar", "clinvar"),
        ("--online-gnomad", "population"),
        ("--online-vep", "computational"),
    ]:
        exit_code = main(
            [
                "rate",
                "--gene",
                "ALPL",
                "--chromosome",
                "1",
                "--position",
                "21563117",
                "--ref",
                "A",
                "--alt",
                "C",
                "--disease",
                "Hypophosphatasia",
                provider_flag,
                "--provider-cache-dir",
                cache_dir,
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 0
        assert payload["data_source_modes"][expected_mode] == "online"
        _assert_no_codes(payload.get("applied_evidence", []), {"PP5", "BP6"})

    exit_code = main(
        [
            "literature-search",
            "--gene",
            "ALPL",
            "--variant",
            "NM_000478.6:c.305A>C",
            "--pmid",
            "36361766",
            "--online-pubmed",
            "--provider-cache-dir",
            cache_dir,
        ]
    )
    literature_payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert literature_payload["applied_evidence"] == []
    assert literature_payload["final_classification_changed"] is False


def test_default_mcp_and_cli_do_not_enable_online_without_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_http(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("default workflow attempted provider HTTP")

    monkeypatch.setattr(ProviderHTTPClient, "request", fail_http)
    exit_code = main(
        [
            "rate",
            "--gene",
            "ALPL",
            "--chromosome",
            "1",
            "--position",
            "21563117",
            "--ref",
            "A",
            "--alt",
            "C",
            "--disease",
            "Hypophosphatasia",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data_source_modes"]["population"] == "mock"

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": {
                "gene": "ALPL",
                "chromosome": "1",
                "position": 21563117,
                "ref": "A",
                "alt": "C",
                "disease": "Hypophosphatasia",
            },
        },
    }
    response = asyncio.run(_server().handle_message(json.dumps(request)))
    assert response["result"]["isError"] is False
