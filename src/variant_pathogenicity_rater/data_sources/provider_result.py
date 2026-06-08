from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.data_sources.config import (
    DataSourceConfig,
    DataSourcesConfig,
    ProviderMode,
)
from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceSource


class ProviderOutcome(StrEnum):
    SUCCESS = "success"
    NO_RECORD = "no_record"
    FAILURE = "failure"
    SKIPPED = "skipped"
    CACHE_HIT = "cache_hit"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ProviderRuntimeResult(SchemaModel):
    provider_name: str = Field(..., min_length=1)
    requested_mode: str = "default"
    configured_mode: str | None = None
    attempted: bool = False
    outcome: ProviderOutcome = ProviderOutcome.SKIPPED
    records_count: int = Field(default=0, ge=0)
    source_version: str | None = None
    query: dict[str, Any] = Field(default_factory=dict)
    endpoint: str | None = None
    cache_hit: bool | None = None
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_type: str | None = None
    error_message_summary: str | None = None
    raw_record_hash: str | None = None
    retrieval_timestamp: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    dependency_status: dict[str, Any] | None = None
    yield_observations: dict[str, Any] = Field(default_factory=dict)


def build_provider_runtime_result(
    *,
    provider_name: str,
    requested_mode: str = "default",
    configured_mode: str | None = None,
    attempted: bool | None = None,
    outcome: str | ProviderOutcome = ProviderOutcome.SKIPPED,
    records_count: int = 0,
    source_version: str | None = None,
    query: dict[str, Any] | None = None,
    endpoint: str | None = None,
    cache_hit: bool | None = None,
    limitations: list[str] | None = None,
    warnings: list[str] | None = None,
    error_type: str | None = None,
    error_message_summary: str | None = None,
    raw_record_hash: str | None = None,
    retrieval_timestamp: str | None = None,
    provenance: dict[str, Any] | None = None,
    dependency_status: dict[str, Any] | None = None,
    yield_observations: dict[str, Any] | None = None,
) -> ProviderRuntimeResult:
    resolved_outcome = ProviderOutcome(str(outcome))
    resolved_attempted = attempted
    if resolved_attempted is None:
        resolved_attempted = resolved_outcome not in {ProviderOutcome.SKIPPED}
    return ProviderRuntimeResult(
        provider_name=provider_name,
        requested_mode=requested_mode,
        configured_mode=configured_mode,
        attempted=resolved_attempted,
        outcome=resolved_outcome,
        records_count=max(0, int(records_count or 0)),
        source_version=source_version,
        query=dict(query or {}),
        endpoint=endpoint,
        cache_hit=cache_hit,
        limitations=_unique(limitations or []),
        warnings=_unique(warnings or []),
        error_type=error_type,
        error_message_summary=_summarize_message(error_message_summary),
        raw_record_hash=raw_record_hash,
        retrieval_timestamp=retrieval_timestamp,
        provenance=dict(provenance or {}),
        dependency_status=dependency_status,
        yield_observations=dict(yield_observations or {}),
    )


def provider_result_from_source(
    *,
    provider_name: str,
    source: EvidenceSource | dict[str, Any],
    requested_mode: str = "default",
    configured_mode: str | None = None,
    records_count: int = 1,
    outcome: str | ProviderOutcome | None = None,
    limitations: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ProviderRuntimeResult:
    source_payload = _source_payload(source)
    provenance = _provider_provenance(source_payload)
    missing_limitations = []
    if not provenance:
        missing_limitations.append("Provider provenance is unavailable for runtime summary.")
    resolved_outcome = outcome
    if resolved_outcome is None:
        resolved_outcome = ProviderOutcome.CACHE_HIT if provenance.get("cache_hit") is True else ProviderOutcome.SUCCESS
    return build_provider_runtime_result(
        provider_name=provider_name,
        requested_mode=requested_mode,
        configured_mode=configured_mode,
        attempted=True,
        outcome=resolved_outcome,
        records_count=records_count,
        source_version=_provider_source_version(None, source_payload, provenance),
        query=provenance.get("query") or source_payload.get("query"),
        endpoint=provenance.get("endpoint") or provenance.get("source_url") or provenance.get("request_url") or source_payload.get("endpoint") or source_payload.get("url"),
        cache_hit=provenance.get("cache_hit"),
        limitations=[*(limitations or []), *missing_limitations, *list(provenance.get("limitations") or [])],
        warnings=warnings,
        raw_record_hash=provenance.get("raw_record_hash") or source_payload.get("raw_snapshot_ref"),
        retrieval_timestamp=provenance.get("retrieved_at") or source_payload.get("retrieval_timestamp"),
        provenance=provenance,
    )


def provider_result_from_failure(
    *,
    provider_name: str,
    requested_mode: str = "default",
    configured_mode: str | None = None,
    error: Exception | str | None = None,
    limitations: list[str] | None = None,
    source_version: str | None = None,
    query: dict[str, Any] | None = None,
    endpoint: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> ProviderRuntimeResult:
    error_type = type(error).__name__ if isinstance(error, Exception) else None
    message = str(error) if error is not None else None
    return build_provider_runtime_result(
        provider_name=provider_name,
        requested_mode=requested_mode,
        configured_mode=configured_mode,
        attempted=True,
        outcome=ProviderOutcome.FAILURE,
        records_count=0,
        source_version=source_version or (provenance or {}).get("source_version"),
        query=query or (provenance or {}).get("query"),
        endpoint=endpoint or (provenance or {}).get("endpoint"),
        cache_hit=(provenance or {}).get("cache_hit"),
        limitations=limitations or ([message] if message else []),
        error_type=error_type,
        error_message_summary=message,
        raw_record_hash=(provenance or {}).get("raw_record_hash"),
        retrieval_timestamp=(provenance or {}).get("retrieved_at"),
        provenance=provenance or {},
    )


def provider_result_from_skipped(
    *,
    provider_name: str,
    requested_mode: str = "default",
    configured_mode: str | None = None,
    limitations: list[str] | None = None,
) -> ProviderRuntimeResult:
    return build_provider_runtime_result(
        provider_name=provider_name,
        requested_mode=requested_mode,
        configured_mode=configured_mode,
        attempted=False,
        outcome=ProviderOutcome.SKIPPED,
        records_count=0,
        limitations=limitations,
    )


def provider_result_from_no_record(
    *,
    provider_name: str,
    requested_mode: str = "default",
    configured_mode: str | None = None,
    source_version: str | None = None,
    query: dict[str, Any] | None = None,
    endpoint: str | None = None,
    cache_hit: bool | None = None,
    limitations: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> ProviderRuntimeResult:
    return build_provider_runtime_result(
        provider_name=provider_name,
        requested_mode=requested_mode,
        configured_mode=configured_mode,
        attempted=True,
        outcome=ProviderOutcome.NO_RECORD,
        records_count=0,
        source_version=source_version or (provenance or {}).get("source_version"),
        query=query or (provenance or {}).get("query"),
        endpoint=endpoint or (provenance or {}).get("endpoint"),
        cache_hit=cache_hit if cache_hit is not None else (provenance or {}).get("cache_hit"),
        limitations=limitations,
        raw_record_hash=(provenance or {}).get("raw_record_hash"),
        retrieval_timestamp=(provenance or {}).get("retrieved_at"),
        provenance=provenance or {},
    )


def provider_result_from_step_payload(
    *,
    provider_name: str,
    source_config: DataSourceConfig,
    step_name: str,
    step_payload: Any,
    requested_mode: str,
) -> ProviderRuntimeResult:
    if step_payload is None:
        return provider_result_from_skipped(
            provider_name=provider_name,
            requested_mode=requested_mode,
            configured_mode=str(source_config.mode),
            limitations=list(source_config.limitations or []),
        )
    yield_obs = _yield_observations_from_step(step_name, step_payload)
    dependency_status = _provider_dependency_status(step_payload)
    if dependency_status and dependency_status.get("satisfied") is False:
        limitations = _provider_limitations(step_payload)
        source_payload = _provider_source_payload(step_payload)
        provenance = _provider_provenance(source_payload)
        return build_provider_runtime_result(
            provider_name=provider_name,
            requested_mode=requested_mode,
            configured_mode=str(source_config.mode),
            attempted=False,
            outcome=ProviderOutcome.SKIPPED,
            records_count=0,
            source_version=_provider_source_version(source_config, source_payload, provenance),
            query=provenance.get("query") or source_payload.get("query"),
            endpoint=provenance.get("endpoint") or provenance.get("source_url") or provenance.get("request_url") or source_payload.get("endpoint") or source_payload.get("url"),
            cache_hit=provenance.get("cache_hit"),
            limitations=limitations,
            warnings=_provider_warnings(step_payload),
            raw_record_hash=provenance.get("raw_record_hash") or source_payload.get("raw_snapshot_ref"),
            retrieval_timestamp=provenance.get("retrieved_at") or source_payload.get("retrieval_timestamp"),
            provenance=provenance,
            dependency_status=dependency_status,
            yield_observations=yield_obs,
        )

    limitations = _provider_limitations(step_payload)
    warnings = _provider_warnings(step_payload)
    source_payload = _provider_source_payload(step_payload)
    provenance = _provider_provenance(source_payload)
    records_count = _provider_records_count(step_payload, step_name)
    outcome = _provider_outcome(
        configured_mode=str(source_config.mode),
        step_payload=step_payload,
        records_count=records_count,
        limitations=limitations,
        provenance=provenance,
    )
    error_type = _error_type_from_limitations(limitations) if outcome == ProviderOutcome.FAILURE else None
    error_summary = _error_summary_from_limitations(limitations) if outcome == ProviderOutcome.FAILURE else None
    return build_provider_runtime_result(
        provider_name=provider_name,
        requested_mode=requested_mode,
        configured_mode=str(source_config.mode),
        attempted=True,
        outcome=outcome,
        records_count=records_count,
        source_version=_provider_source_version(source_config, source_payload, provenance),
        query=provenance.get("query") or source_payload.get("query"),
        endpoint=provenance.get("endpoint") or provenance.get("source_url") or provenance.get("request_url") or source_payload.get("endpoint") or source_payload.get("url"),
        cache_hit=provenance.get("cache_hit"),
        limitations=limitations,
        warnings=warnings,
        error_type=error_type,
        error_message_summary=error_summary,
        raw_record_hash=provenance.get("raw_record_hash") or source_payload.get("raw_snapshot_ref"),
        retrieval_timestamp=provenance.get("retrieved_at") or source_payload.get("retrieval_timestamp"),
        provenance=provenance,
        dependency_status=dependency_status,
        yield_observations=yield_obs,
    )


def build_provider_runtime_results(
    data_sources_config: DataSourcesConfig,
    step_results: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, ProviderRuntimeResult]:
    providers = _provider_specs(step_results, options)
    return {
        name: provider_result_from_step_payload(
            provider_name=name,
            source_config=data_sources_config.source(config["source_name"]),
            step_name=config["step_name"],
            step_payload=step_results.get(config["step_name"]),
            requested_mode=config["requested"],
        )
        for name, config in providers.items()
    }


def provider_summary_from_runtime_results(
    runtime_results: dict[str, ProviderRuntimeResult],
) -> dict[str, Any]:
    return {
        name: _legacy_summary_item(result)
        for name, result in runtime_results.items()
    }


def build_provider_summary(
    data_sources_config: DataSourcesConfig,
    step_results: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    return provider_summary_from_runtime_results(
        build_provider_runtime_results(
            data_sources_config,
            step_results,
            options,
        )
    )


def provider_runtime_results_to_json(
    runtime_results: dict[str, ProviderRuntimeResult],
) -> dict[str, Any]:
    return {
        name: result.model_dump(mode="json")
        for name, result in runtime_results.items()
    }


def provider_runtime_results_json(
    data_sources_config: DataSourcesConfig,
    step_results: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    return provider_runtime_results_to_json(
        build_provider_runtime_results(
            data_sources_config,
            step_results,
            options,
        )
    )


def provider_summary_from_runtime_json(
    runtime_json: dict[str, Any],
) -> dict[str, Any]:
    """Project legacy ``provider_mode_summary`` from serialized
    ``step_results.provider_runtime``.

    Each entry is validated as a ``ProviderRuntimeResult`` and then
    projected through ``_legacy_summary_item`` so the output shape
    matches ``provider_summary_from_runtime_results``.
    """
    summary: dict[str, Any] = {}
    for name, payload in runtime_json.items():
        if not isinstance(payload, dict):
            continue
        try:
            result = ProviderRuntimeResult.model_validate(payload)
        except Exception:
            continue
        summary[name] = _legacy_summary_item(result)
    return summary


def _legacy_summary_item(result: ProviderRuntimeResult) -> dict[str, Any]:
    provider_mode = result.provenance.get("provider_mode") or result.configured_mode
    return {
        "requested_mode": result.requested_mode,
        "configured_mode": result.configured_mode,
        "actual_outcome": str(result.outcome),
        "source_version": result.source_version,
        "endpoint": result.endpoint,
        "query": result.query,
        "raw_hash": result.raw_record_hash,
        "cache_hit": result.cache_hit,
        "provider_mode": provider_mode,
        "records_count": result.records_count,
        "limitations_count": len(result.limitations),
        "limitations": result.limitations,
        "attempted": result.attempted,
        "outcome": str(result.outcome),
        "warnings": result.warnings,
        "error_type": result.error_type,
        "error_message_summary": result.error_message_summary,
        "raw_record_hash": result.raw_record_hash,
        "retrieval_timestamp": result.retrieval_timestamp,
        "provenance": result.provenance,
        "dependency_status": result.dependency_status,
    }


def _provider_specs(step_results: dict[str, Any], options: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "clinvar": {
            "source_name": "clinvar",
            "step_name": "query_clinvar",
            "requested": _requested_provider_mode(options, "use_online_clinvar", "clinvar"),
        },
        "population": {
            "source_name": "population",
            "step_name": "query_population_frequency",
            "requested": _requested_provider_mode(options, "use_online_gnomad", "population"),
        },
        "computational": {
            "source_name": "computational",
            "step_name": "evaluate_computational_evidence",
            "requested": _requested_provider_mode(options, "use_online_vep", "computational"),
        },
        "literature": {
            "source_name": "literature",
            "step_name": (
                "search_and_summarize_literature"
                if "search_and_summarize_literature" in step_results
                else "search_literature_evidence"
            ),
            "requested": (
                "online"
                if options.get("use_online_pubmed") or options.get("use_online_litvar")
                else _requested_provider_mode(options, "use_online_pubmed", "literature")
            ),
        },
        "clingen_erepo": {
            "source_name": "clingen_erepo",
            "step_name": "query_clingen_erepo",
            "requested": "included" if options.get("include_clingen_erepo") else "default",
        },
    }


def _provider_outcome(
    *,
    configured_mode: str,
    step_payload: Any,
    records_count: int,
    limitations: list[str],
    provenance: dict[str, Any],
) -> ProviderOutcome:
    if step_payload is None:
        return ProviderOutcome.SKIPPED
    if provenance.get("cache_hit") is True:
        return ProviderOutcome.CACHE_HIT
    lowered = " ".join(limitations).lower()
    if "failed:" in lowered or " failure " in f" {lowered} " or "query failed" in lowered:
        return ProviderOutcome.FAILURE
    if records_count > 0 and ("partial" in lowered or "incomplete" in lowered):
        return ProviderOutcome.PARTIAL
    if records_count == 0 and ("no " in lowered and "record" in lowered):
        return ProviderOutcome.NO_RECORD
    if records_count == 0 and configured_mode in {str(ProviderMode.ONLINE), "online"}:
        return ProviderOutcome.NO_RECORD
    if records_count == 0 and lowered and "unavailable" in lowered:
        return ProviderOutcome.UNAVAILABLE
    return ProviderOutcome.SUCCESS


def _provider_records_count(step_payload: Any, step_name: str) -> int:
    if not isinstance(step_payload, dict):
        return 0
    if isinstance(step_payload.get("records"), list):
        return len(step_payload["records"])
    if isinstance(step_payload.get("literature_search_results"), list):
        return len(step_payload["literature_search_results"])
    if step_name == "query_population_frequency":
        if step_payload.get("overall_af") is not None or step_payload.get("max_pop_af") is not None:
            return 1
        return 0
    if step_name == "evaluate_computational_evidence":
        summary = step_payload.get("summary") if isinstance(step_payload.get("summary"), dict) else {}
        return len(summary.get("predictor_calls") or [])
    if isinstance(step_payload.get("matches"), list):
        return len(step_payload["matches"])
    return 0


def _provider_source_payload(step_payload: Any) -> dict[str, Any]:
    if not isinstance(step_payload, dict):
        return {}
    source = step_payload.get("source")
    if isinstance(source, dict):
        return source
    records = step_payload.get("records")
    if isinstance(records, list) and records:
        first = records[0] if isinstance(records[0], dict) else {}
        source = first.get("source") if isinstance(first, dict) else None
        if isinstance(source, dict):
            return source
    summary = step_payload.get("summary")
    if isinstance(summary, dict):
        for call in summary.get("predictor_calls") or []:
            if isinstance(call, dict) and isinstance(call.get("provenance"), dict):
                return {"provenance": call["provenance"], "version": call.get("source_version")}
    provenance = step_payload.get("provenance")
    if isinstance(provenance, dict):
        return {"provenance": provenance}
    if isinstance(provenance, list) and provenance:
        first = provenance[0]
        if isinstance(first, dict):
            return {"provenance": first}
    return {}


def _provider_provenance(source_payload: dict[str, Any]) -> dict[str, Any]:
    provenance = source_payload.get("provenance")
    if hasattr(provenance, "model_dump"):
        return provenance.model_dump(mode="json")
    if isinstance(provenance, dict):
        return provenance
    return {}


def _provider_dependency_status(step_payload: Any) -> dict[str, Any] | None:
    if not isinstance(step_payload, dict):
        return None
    payload = step_payload.get("provider_dependency")
    if isinstance(payload, dict):
        return payload
    provenance = step_payload.get("provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get("provider_dependency"), dict):
        return provenance["provider_dependency"]
    return None


def _provider_limitations(step_payload: Any) -> list[str]:
    if not isinstance(step_payload, dict):
        return []
    limitations = [str(item) for item in step_payload.get("limitations") or [] if item]
    summary = step_payload.get("summary")
    if isinstance(summary, dict):
        decision = summary.get("decision")
        if isinstance(decision, dict):
            limitations.extend(str(item) for item in decision.get("limitations") or [] if item)
        for call in summary.get("predictor_calls") or []:
            if isinstance(call, dict):
                limitations.extend(str(item) for item in call.get("limitations") or [] if item)
    return _unique(limitations)


def _provider_warnings(step_payload: Any) -> list[str]:
    if not isinstance(step_payload, dict):
        return []
    warnings = [str(item) for item in step_payload.get("warnings") or [] if item]
    for key in ("review_flags", "blocking_flags"):
        for flag in step_payload.get(key) or []:
            if isinstance(flag, dict) and flag.get("message"):
                warnings.append(str(flag["message"]))
    return _unique(warnings)


def _yield_observations_from_step(step_name: str, step_payload: Any) -> dict[str, Any]:
    """Extract non-semantic yield observations from raw step payloads.

    This is the only place that reads raw step payload shapes for yield
    metrics.  Benchmark and reporting consumers read ``yield_observations``
    from ``ProviderRuntimeResult`` instead of interpreting raw steps.
    """
    if not isinstance(step_payload, dict):
        return {}
    if step_name == "query_clinvar":
        return {
            "candidate_evidence_count": len(step_payload.get("candidate_evidence_items") or []),
        }
    if step_name == "query_population_frequency":
        data_source = step_payload.get("data_source")
        return {
            "data_source": str(data_source) if data_source else None,
        }
    if step_name in ("search_and_summarize_literature", "search_literature_evidence"):
        records = _literature_yield_records(step_payload)
        return {
            "pubmed_citations": sum(1 for r in records if _record_source_name(r) == "pubmed"),
            "litvar_citations": sum(1 for r in records if _record_source_name(r) == "litvar"),
            "summary_generated": bool(
                step_payload.get("criterion_summaries") or step_payload.get("summary")
            ),
        }
    return {}


def _literature_yield_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("literature_records", "literature_search_results", "records"):
        records = payload.get(key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    return []


def _record_source_name(record: dict[str, Any]) -> str:
    source = record.get("source")
    if isinstance(source, dict):
        source = source.get("name") or source.get("source")
    return str(source or record.get("data_source") or "").lower()


def _provider_source_version(
    source: DataSourceConfig | None,
    source_payload: dict[str, Any],
    provenance: dict[str, Any],
) -> str | None:
    return (
        provenance.get("source_version")
        or source_payload.get("version")
        or source_payload.get("source_version")
        or (source.source_version if source is not None else None)
    )


def _requested_provider_mode(
    options: dict[str, Any],
    online_flag: str,
    source_name: str,
) -> str:
    if options.get(online_flag):
        return "online"
    source_override = (
        (options.get("data_sources") or {}).get("sources", {}).get(source_name)
        if isinstance(options.get("data_sources"), dict)
        else None
    )
    if isinstance(source_override, dict) and source_override.get("mode"):
        return str(source_override["mode"])
    return "default"


def _source_payload(source: EvidenceSource | dict[str, Any]) -> dict[str, Any]:
    if hasattr(source, "model_dump"):
        return source.model_dump(mode="json")
    return dict(source)


def _error_type_from_limitations(limitations: list[str]) -> str | None:
    for item in limitations:
        if "failed:" in item.lower():
            return item.split("failed:", 1)[0].strip().replace(" ", "_") or "ProviderFailure"
    return "ProviderFailure" if limitations else None


def _error_summary_from_limitations(limitations: list[str]) -> str | None:
    for item in limitations:
        if "failed:" in item.lower() or "query failed" in item.lower() or "failure" in item.lower():
            return _summarize_message(item)
    return _summarize_message(limitations[0]) if limitations else None


def _summarize_message(message: str | None, *, limit: int = 240) -> str | None:
    if not message:
        return None
    text = " ".join(str(message).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _unique(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique
