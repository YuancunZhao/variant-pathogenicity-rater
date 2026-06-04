from __future__ import annotations

from variant_pathogenicity_rater.data_sources.config import (
    DataSourceConfig,
    DataSourcesConfig,
    ProviderMode,
)
from variant_pathogenicity_rater.data_sources.provider_result import (
    ProviderOutcome,
    build_provider_summary,
    provider_result_from_failure,
    provider_result_from_no_record,
    provider_result_from_skipped,
    provider_result_from_source,
)
from variant_pathogenicity_rater.data_sources.provenance import provenance_from_raw_record
from variant_pathogenicity_rater.schemas.evidence import EvidenceSource


def _source(name: str, *, provider_mode: str = "online") -> EvidenceSource:
    provenance = provenance_from_raw_record(
        data_source=name,
        source_version=f"{name}-v1",
        query={"variant_id": "1-21563117-A-C"},
        raw_record={"id": "record-1", "source": name},
        endpoint=f"https://example.org/{name}",
        provider_mode=provider_mode,
        cache_hit=False,
    )
    return EvidenceSource(
        name=name,
        version=f"{name}-v1",
        retrieval_timestamp=provenance.retrieved_at,
        query={"variant_id": "1-21563117-A-C"},
        raw_snapshot_ref=provenance.raw_record_hash,
        provenance=provenance,
    )


def test_provider_result_from_source_maps_clinvar_source() -> None:
    result = provider_result_from_source(
        provider_name="clinvar",
        source=_source("clinvar"),
        requested_mode="online",
        configured_mode="online",
    )

    assert result.provider_name == "clinvar"
    assert result.outcome == ProviderOutcome.SUCCESS
    assert result.attempted is True
    assert result.source_version == "clinvar-v1"
    assert result.query == {"variant_id": "1-21563117-A-C"}
    assert result.endpoint == "https://example.org/clinvar"
    assert result.cache_hit is False
    assert result.raw_record_hash
    assert result.retrieval_timestamp
    assert result.provenance["provider_mode"] == "online"


def test_provider_result_from_source_maps_population_source() -> None:
    result = provider_result_from_source(
        provider_name="population",
        source=_source("gnomad", provider_mode="online"),
        requested_mode="online",
        configured_mode="online",
    )

    assert result.provider_name == "population"
    assert result.outcome == ProviderOutcome.SUCCESS
    assert result.source_version == "gnomad-v1"
    assert result.query["variant_id"] == "1-21563117-A-C"
    assert result.endpoint == "https://example.org/gnomad"


def test_provider_result_from_failure_sets_failure_fields() -> None:
    result = provider_result_from_failure(
        provider_name="computational",
        requested_mode="online",
        configured_mode="online",
        error=TimeoutError("VEP timed out after 10 seconds"),
    )

    assert result.attempted is True
    assert result.outcome == ProviderOutcome.FAILURE
    assert result.error_type == "TimeoutError"
    assert result.error_message_summary == "VEP timed out after 10 seconds"


def test_provider_result_from_no_record_has_no_evidence_implication() -> None:
    result = provider_result_from_no_record(
        provider_name="population",
        requested_mode="online",
        configured_mode="online",
        query={"variant_id": "1-21563117-A-C"},
        limitations=["No gnomAD record was returned; this is not absence evidence."],
    )

    assert result.outcome == ProviderOutcome.NO_RECORD
    assert result.records_count == 0
    assert result.attempted is True
    assert "not absence evidence" in result.limitations[0]


def test_provider_result_from_skipped_sets_attempted_false() -> None:
    result = provider_result_from_skipped(
        provider_name="clingen_erepo",
        requested_mode="default",
        configured_mode="mock",
    )

    assert result.outcome == ProviderOutcome.SKIPPED
    assert result.attempted is False
    assert result.records_count == 0


def test_missing_provenance_does_not_crash_and_adds_limitation() -> None:
    result = provider_result_from_source(
        provider_name="clinvar",
        source=EvidenceSource(name="ClinVar"),
    )

    assert result.outcome == ProviderOutcome.SUCCESS
    assert result.provenance == {}
    assert any("provenance is unavailable" in item for item in result.limitations)


def test_build_provider_summary_preserves_legacy_shape_and_adds_runtime_fields() -> None:
    step_results = {
        "query_clinvar": {
            "records": [{"source": _source("clinvar").model_dump(mode="json")}],
            "limitations": [],
        }
    }
    config = DataSourcesConfig(
        sources={
            "clinvar": DataSourceConfig(name="clinvar", mode=ProviderMode.ONLINE),
            "population": DataSourceConfig(name="population", mode=ProviderMode.MOCK),
            "computational": DataSourceConfig(name="computational", mode=ProviderMode.MOCK),
            "literature": DataSourceConfig(name="literature", mode=ProviderMode.MOCK),
            "clingen_erepo": DataSourceConfig(name="clingen_erepo", mode=ProviderMode.MOCK),
        }
    )

    summary = build_provider_summary(config, step_results, {"use_online_clinvar": True})
    clinvar = summary["clinvar"]

    assert clinvar["requested_mode"] == "online"
    assert clinvar["configured_mode"] == "online"
    assert clinvar["actual_outcome"] == "success"
    assert clinvar["outcome"] == "success"
    assert clinvar["raw_hash"] == clinvar["raw_record_hash"]
    assert clinvar["limitations_count"] == 0
    assert clinvar["attempted"] is True
