from __future__ import annotations

from variant_pathogenicity_rater.data_sources.config import (
    DataSourceConfig,
    DataSourcesConfig,
    ProviderMode,
)
from variant_pathogenicity_rater.data_sources.provider_result import (
    ProviderOutcome,
    build_provider_runtime_results,
    build_provider_summary,
    provider_entry_from_runtime_json,
    provider_runtime_results_to_json,
    provider_result_from_failure,
    provider_result_from_no_record,
    provider_result_from_skipped,
    provider_result_from_source,
    provider_summary_from_runtime_json,
    provider_summary_from_runtime_results,
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


def test_provider_summary_and_runtime_json_share_one_runtime_source() -> None:
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

    runtime_results = build_provider_runtime_results(
        config,
        step_results,
        {"use_online_clinvar": True},
    )
    summary = provider_summary_from_runtime_results(runtime_results)
    runtime_json = provider_runtime_results_to_json(runtime_results)

    assert runtime_json["clinvar"]["outcome"] == "success"
    assert summary["clinvar"]["outcome"] == runtime_json["clinvar"]["outcome"]
    assert summary["clinvar"]["actual_outcome"] == runtime_json["clinvar"]["outcome"]
    assert summary["clinvar"]["raw_record_hash"] == runtime_json["clinvar"]["raw_record_hash"]
    assert summary["clinvar"]["raw_hash"] == runtime_json["clinvar"]["raw_record_hash"]


# ── provider_entry_from_runtime_json / malformed runtime tests ──


def test_provider_entry_from_runtime_json_projects_valid_payload() -> None:
    payload = {
        "requested_mode": "online",
        "configured_mode": "online",
        "attempted": True,
        "outcome": "success",
        "records_count": 3,
        "source_version": "clinvar-v2",
        "query": {"variant_id": "1-100-A-G"},
        "endpoint": "https://clinvar.example/api",
        "cache_hit": False,
        "limitations": [],
        "warnings": [],
        "raw_record_hash": "abc123",
        "retrieval_timestamp": "2025-01-01T00:00:00Z",
        "provenance": {"provider_mode": "online"},
    }

    entry = provider_entry_from_runtime_json("clinvar", payload)

    assert entry["requested_mode"] == "online"
    assert entry["outcome"] == "success"
    assert entry["records_count"] == 3
    assert entry["source_version"] == "clinvar-v2"
    assert entry["endpoint"] == "https://clinvar.example/api"
    assert entry["cache_hit"] is False
    assert entry["provenance"]["provider_mode"] == "online"


def test_provider_entry_from_runtime_json_returns_fallback_for_none() -> None:
    entry = provider_entry_from_runtime_json("clinvar", None)

    assert entry["requested_mode"] == "default"
    assert entry["outcome"] == "skipped"
    assert entry["attempted"] is False
    assert entry["records_count"] == 0


def test_provider_entry_from_runtime_json_returns_fallback_for_non_dict() -> None:
    entry = provider_entry_from_runtime_json("population", "not_a_dict")

    assert entry["outcome"] == "skipped"
    assert entry["attempted"] is False


def test_provider_entry_from_runtime_json_returns_fallback_for_malformed() -> None:
    # Missing required provider_name — validation should fail gracefully.
    entry = provider_entry_from_runtime_json("clinvar", {"outcome": "bogus_value"})

    assert entry["outcome"] == "skipped"
    assert entry["attempted"] is False
    assert entry["records_count"] == 0


def test_provider_summary_from_runtime_json_known_malformed_entries_get_fallback() -> None:
    """Known provider keys with malformed runtime entries must receive a safe
    skipped fallback, not be silently omitted from providers.summary."""
    mixed = {
        "clinvar": {
            "requested_mode": "online",
            "outcome": "success",
            "records_count": 5,
            "attempted": True,
        },
        "population": "garbage_not_a_dict",
        "computational": {
            "outcome": "partial",
            "records_count": 2,
        },
        "unknown_garbage_key": {"foo": "bar"},
    }

    summary = provider_summary_from_runtime_json(mixed)

    # Valid entries project normally.
    assert "clinvar" in summary
    assert summary["clinvar"]["outcome"] == "success"
    assert "computational" in summary
    assert summary["computational"]["outcome"] == "partial"

    # Known provider with non-dict payload → safe skipped fallback.
    assert "population" in summary
    assert summary["population"]["outcome"] == "skipped"
    assert summary["population"]["attempted"] is False
    assert summary["population"]["records_count"] == 0

    # Unknown garbage key must not pollute the summary.
    assert "unknown_garbage_key" not in summary


def test_provider_summary_from_runtime_json_malformed_dict_gets_fallback() -> None:
    """A dict entry that fails ProviderRuntimeResult validation for a known
    provider must receive a safe skipped fallback."""
    runtime = {
        "clinvar": {"not_a_valid_field": object()},  # un-serializable garbage
    }

    summary = provider_summary_from_runtime_json(runtime)

    assert "clinvar" in summary
    assert summary["clinvar"]["outcome"] == "skipped"
    assert summary["clinvar"]["attempted"] is False
    assert summary["clinvar"]["records_count"] == 0

    # providers.summary fallback must be consistent with provider_entry fallback.
    entry = provider_entry_from_runtime_json("clinvar", {"not_a_valid_field": "x"})
    assert entry["outcome"] == "skipped"
    assert entry["attempted"] is summary["clinvar"]["attempted"]
    assert entry["records_count"] == summary["clinvar"]["records_count"]


def test_provider_summary_from_runtime_json_empty_runtime_returns_empty_summary() -> None:
    assert provider_summary_from_runtime_json({}) == {}


def test_build_provider_summary_produces_entries_that_can_be_round_tripped() -> None:
    """Canonical provider_entry_from_runtime_json must be consistent with
    build_provider_summary output for the same step payload."""
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

    runtime_results = build_provider_runtime_results(config, step_results, {"use_online_clinvar": True})
    runtime_json = provider_runtime_results_to_json(runtime_results)
    summary = provider_summary_from_runtime_results(runtime_results)

    # Each runtime-backed provider entry should project consistently.
    for name in ("clinvar", "population", "computational", "literature", "clingen_erepo"):
        entry = provider_entry_from_runtime_json(name, runtime_json.get(name))
        assert entry["outcome"] == runtime_json[name]["outcome"]
        assert entry["attempted"] == runtime_json[name]["attempted"]
        assert entry["records_count"] == runtime_json[name]["records_count"]
        # Legacy summary must match the canonical entry outcome.
        assert entry["outcome"] == summary[name]["outcome"]
