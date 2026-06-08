from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient
from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
    raw_record_hash,
)
from variant_pathogenicity_rater.evidence.population import PopulationFrequencyProvider
from variant_pathogenicity_rater.schemas.evidence import EvidenceSource, PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import Variant


GNOMAD_GRAPHQL_ENDPOINT = "https://gnomad.broadinstitute.org/api"
GNOMAD_FULL_QUERY_NAME = "VariantFullWithOptionalPopulation"
GNOMAD_FULL_QUERY_VERSION = "v1_optional_population_legacy"
GNOMAD_FREQUENCY_QUERY_NAME = "VariantFrequency"
GNOMAD_FREQUENCY_QUERY_VERSION = "v2_exome_genome_stable"
GNOMAD_MINIMAL_QUERY_NAME = "VariantMinimal"
GNOMAD_MINIMAL_QUERY_VERSION = "v1_minimal_identity"

GNOMAD_FULL_QUERY = """
query VariantFullWithOptionalPopulation($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variantId
    chrom
    pos
    ref
    alt
    genome { ac an af homozygote_count hemizygote_count }
    exome { ac an af homozygote_count hemizygote_count }
    populations {
      id
      ac
      an
      af
      homozygote_count
      hemizygote_count
    }
    faf95 { population faf95 }
  }
}
"""
GNOMAD_FREQUENCY_QUERY = """
query VariantFrequency($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variantId
    chrom
    pos
    ref
    alt
    genome { ac an af homozygote_count hemizygote_count }
    exome { ac an af homozygote_count hemizygote_count }
  }
}
"""
GNOMAD_MINIMAL_QUERY = """
query VariantMinimal($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variantId
    chrom
    pos
    ref
    alt
  }
}
"""


class GnomADOnlineProvider(PopulationFrequencyProvider):
    def __init__(
        self,
        config: DataSourceConfig,
        *,
        http_client: Any | None = None,
        dataset: str = "gnomad_r4",
    ) -> None:
        if not config.online_enabled:
            raise RuntimeError("gnomAD online mode requires explicit online_enabled=true.")
        self.config = config
        self.dataset = dataset
        self.cache = DiskCache(config.cache_dir or ".cache/variant_pathogenicity_rater/gnomad")
        self.http_client = http_client or ProviderHTTPClient(config)

    def query(self, variant: Variant) -> PopulationFrequency:
        query = {
            "variant_id": _gnomad_variant_id(variant),
            "dataset": self.dataset,
            "genome_build": variant.genome_build,
            "chrom": variant.chrom,
            "pos": variant.pos,
            "ref": variant.ref,
            "alt": variant.alt,
        }
        try:
            entry, cache_hit = self.cache.get_or_set(
                provider=self.config.name,
                mode=str(self.config.mode),
                source_version=self._source_version(),
                query=query,
                loader=lambda: self._load_payload(query),
                ttl_seconds=self.config.ttl_seconds,
            )
            return _frequency_from_payload(
                entry.payload,
                variant,
                query,
                config=self.config,
                source_version=self._source_version(),
                dataset=self.dataset,
                cache_hit=cache_hit,
            )
        except Exception as exc:  # noqa: BLE001 - provider failure must degrade.
            raw_error = _error_payload(exc)
            request_payload = _request_payload(
                query["variant_id"],
                self.dataset,
                query_text=GNOMAD_FREQUENCY_QUERY,
                query_name=GNOMAD_FREQUENCY_QUERY_NAME,
                query_version=GNOMAD_FREQUENCY_QUERY_VERSION,
            )
            return _empty_frequency(
                variant=variant,
                query=query,
                config=self.config,
                source_version=self._source_version(),
                raw_payload={
                    "provider": "gnomAD",
                    "query": query,
                    "request_payload": request_payload,
                    "request_payload_hash": raw_record_hash(request_payload),
                    "graphql_query_name": GNOMAD_FREQUENCY_QUERY_NAME,
                    "graphql_query_version": GNOMAD_FREQUENCY_QUERY_VERSION,
                    "dataset": self.dataset,
                    "variant_id": query["variant_id"],
                    "endpoint": GNOMAD_GRAPHQL_ENDPOINT,
                    "error": raw_error,
                },
                limitations=[
                    f"gnomAD online query failed: {exc.__class__.__name__}: {exc}",
                    *_error_limitations(raw_error),
                    "gnomAD online failure was captured as a limitation; interpretation continued.",
                    "Provider failure is not evidence of population absence and cannot trigger PM2_Supporting.",
                ],
                cache_hit=False,
            )

    def _load_payload(self, query: dict[str, Any]) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        payload: dict[str, Any] | None = None
        selected_stage: dict[str, str] | None = None
        final_error: Exception | None = None
        for stage in _query_stages():
            request_payload = _request_payload(
                query["variant_id"],
                self.dataset,
                query_text=stage["query_text"],
                query_name=stage["query_name"],
                query_version=stage["query_version"],
            )
            try:
                candidate = self.http_client.post_json(GNOMAD_GRAPHQL_ENDPOINT, request_payload)
            except Exception as exc:  # noqa: BLE001 - fallback turns provider drift into diagnostics.
                final_error = exc
                attempts.append(_attempt_from_exception(stage, request_payload, exc))
                continue
            errors = candidate.get("errors") if isinstance(candidate, dict) else None
            variant_payload = ((candidate.get("data") or {}).get("variant") if isinstance(candidate, dict) else None)
            attempt = _attempt_from_payload(stage, request_payload, candidate)
            attempts.append(attempt)
            if errors and stage["query_name"] != GNOMAD_MINIMAL_QUERY_NAME:
                continue
            payload = candidate
            selected_stage = stage
            if variant_payload is None and stage["query_name"] != GNOMAD_MINIMAL_QUERY_NAME:
                continue
            break
        if payload is None or selected_stage is None:
            selected_stage = _query_stages()[-1]
            error_payload = _error_payload(final_error) if final_error is not None else {"message": "No gnomAD response payload was available."}
            payload = {
                "errors": [{"message": _provider_error_summary(error_payload)}],
                "data": {"variant": None},
            }
        request_payload = _request_payload(
            query["variant_id"],
            self.dataset,
            query_text=selected_stage["query_text"],
            query_name=selected_stage["query_name"],
            query_version=selected_stage["query_version"],
        )
        return {
            "provider": "GnomADOnlineProvider",
            "source_version": self._source_version(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": GNOMAD_GRAPHQL_ENDPOINT,
            "query": query,
            "dataset": self.dataset,
            "variant_id": query["variant_id"],
            "graphql_query_name": selected_stage["query_name"],
            "graphql_query_version": selected_stage["query_version"],
            "attempts": attempts,
            "request_payload": request_payload,
            "request_payload_hash": raw_record_hash(request_payload),
            "payload": payload,
        }

    def _source_version(self) -> str:
        return self.config.source_version or f"gnomAD {self.dataset} live GraphQL"


def _gnomad_variant_id(variant: Variant) -> str:
    return f"{variant.chrom.removeprefix('chr')}-{variant.pos}-{variant.ref}-{variant.alt}"


def _frequency_from_payload(
    payload: dict[str, Any],
    variant: Variant,
    query: dict[str, Any],
    *,
    config: DataSourceConfig,
    source_version: str,
    dataset: str,
    cache_hit: bool,
) -> PopulationFrequency:
    errors = (payload.get("payload") or {}).get("errors")
    raw = (payload.get("payload") or {}).get("data", {}).get("variant")
    if errors and not _is_variant_not_found_payload(payload):
        error_summary = _graphql_error_summary(errors)
        return _empty_frequency(
            variant=variant,
            query=query,
            config=config,
            source_version=source_version,
            raw_payload=payload,
            cache_hit=cache_hit,
            limitations=[
                f"gnomAD online query failed: GraphQL errors: {error_summary}",
                "gnomAD GraphQL error payload was captured for provider diagnostics.",
                *_attempt_limitations(payload, include_failure_terms=True),
                "Provider failure is not evidence of population absence and cannot trigger PM2_Supporting.",
            ],
        )
    if not isinstance(raw, dict):
        return _empty_frequency(
            variant=variant,
            query=query,
            config=config,
            source_version=source_version,
            raw_payload=payload,
            cache_hit=cache_hit,
            limitations=[
                "No gnomAD online record matched the supplied query; this is not evidence of population absence.",
                "gnomAD no_record is not treated as population absence and cannot trigger PM2_Supporting.",
                *_attempt_limitations(payload),
            ],
        )
    genome = raw.get("genome") if isinstance(raw.get("genome"), dict) else {}
    exome = raw.get("exome") if isinstance(raw.get("exome"), dict) else {}
    aggregate = genome if genome.get("an") is not None else exome
    populations = [item for item in raw.get("populations") or [] if isinstance(item, dict)]
    popmax = _popmax(populations)
    faf95 = _faf95(raw.get("faf95"), popmax.get("id") if popmax else None)
    limitations = [
        "gnomAD online source supplies population facts only; BA1/BS1/PM2 require existing rule gates.",
        *_attempt_limitations(payload),
    ]
    if payload.get("graphql_query_name") != GNOMAD_FULL_QUERY_NAME:
        limitations.append(
            "gnomAD optional population/FAF query was not used for final frequency parsing; stable exome/genome fields were used."
        )
    source = EvidenceSource(
        name=config.name,
        version=source_version,
        url="https://gnomad.broadinstitute.org/",
        retrieval_timestamp=payload.get("retrieved_at"),
        query=query,
    )
    frequency = PopulationFrequency(
        source=source,
        overall_af=_float(aggregate.get("af")),
        max_pop_af=_float(popmax.get("af") if popmax else None),
        population_name=str(popmax.get("id") if popmax else "global"),
        allele_count=_int(aggregate.get("ac")),
        allele_number=_int(aggregate.get("an")),
        homozygote_count=_int(aggregate.get("homozygote_count")),
        hemizygote_count=_int(aggregate.get("hemizygote_count")),
        data_source=config.name,
        filter_status=None,
        data_version=source_version,
        is_absent=False,
        faf95=faf95,
        filtering_af=faf95,
        genome_build=str(variant.genome_build),
        dataset_version=source_version,
        coverage_quality="unknown",
        population_match=None,
        limitations=limitations,
    )
    provenance = provenance_from_raw_record(
        data_source=config.name,
        source_version=source_version,
        query=query,
        raw_record=payload,
        parser_version=config.parser_version,
        confidence=0.6,
        source_url="https://gnomad.broadinstitute.org/",
        endpoint=payload.get("endpoint") or GNOMAD_GRAPHQL_ENDPOINT,
        provider_mode=str(config.mode),
        cache_hit=cache_hit,
        request_method="POST",
        request_url=GNOMAD_GRAPHQL_ENDPOINT,
        dataset=dataset,
        raw_payload_kind="graphql_json",
        ancestry=frequency.population_name,
        population=frequency.population_name,
        allele_number=frequency.allele_number,
        coverage_quality=frequency.coverage_quality,
        limitations=limitations,
    )
    attach_provenance_to_source(source, provenance)
    return frequency


def _empty_frequency(
    *,
    variant: Variant,
    query: dict[str, Any],
    config: DataSourceConfig,
    source_version: str,
    raw_payload: dict[str, Any],
    limitations: list[str],
    cache_hit: bool | None = None,
) -> PopulationFrequency:
    source = EvidenceSource(
        name=config.name,
        version=source_version,
        url="https://gnomad.broadinstitute.org/",
        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
    )
    provenance = provenance_from_raw_record(
        data_source=config.name,
        source_version=source_version,
        query=query,
        raw_record=raw_payload,
        parser_version=config.parser_version,
        confidence=0.2,
        source_url="https://gnomad.broadinstitute.org/",
        endpoint=GNOMAD_GRAPHQL_ENDPOINT,
        provider_mode=str(config.mode),
        cache_hit=cache_hit,
        request_method="POST",
        request_url=GNOMAD_GRAPHQL_ENDPOINT,
        dataset=str(raw_payload.get("dataset") or query.get("dataset") or "gnomAD"),
        raw_payload_kind="graphql_json",
        limitations=limitations,
    )
    attach_provenance_to_source(source, provenance)
    return PopulationFrequency(
        source=source,
        overall_af=None,
        max_pop_af=None,
        population_name="unknown",
        data_source=config.name,
        data_version=source_version,
        is_absent=False,
        genome_build=str(variant.genome_build),
        dataset_version=source_version,
        coverage_quality="unknown",
        population_match=None,
        limitations=limitations,
    )


def _popmax(populations: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [item for item in populations if _float(item.get("af")) is not None]
    return max(usable, key=lambda item: _float(item.get("af")) or 0.0) if usable else {}


def _faf95(values: Any, population: str | None) -> float | None:
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict) and (not population or item.get("population") == population):
                return _float(item.get("faf95") or item.get("faf"))
    if isinstance(values, dict):
        return _float(values.get("faf95") or values.get("faf"))
    return None


def _float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _request_payload(
    variant_id: str,
    dataset: str,
    *,
    query_text: str,
    query_name: str,
    query_version: str,
) -> dict[str, Any]:
    return {
        "query": query_text,
        "operationName": query_name,
        "variables": {"variantId": variant_id, "dataset": dataset},
        "query_metadata": {
            "query_name": query_name,
            "query_version": query_version,
        },
    }


def _graphql_error_summary(errors: Any) -> str:
    if isinstance(errors, list):
        messages = []
        for item in errors[:3]:
            if isinstance(item, dict):
                messages.append(str(item.get("message") or item))
            else:
                messages.append(str(item))
        return "; ".join(messages) or "unspecified GraphQL error"
    return str(errors)


def _error_payload(exc: Exception) -> dict[str, Any]:
    if hasattr(exc, "to_payload"):
        payload = exc.to_payload()
        if isinstance(payload, dict):
            return payload
    return {
        "message": str(exc),
        "cause_type": exc.__class__.__name__,
    }


def _error_limitations(payload: dict[str, Any]) -> list[str]:
    details = []
    if payload.get("status") is not None:
        details.append(f"gnomAD HTTP status: {payload['status']}.")
    if payload.get("response_text"):
        details.append(f"gnomAD HTTP response body summary: {str(payload['response_text'])[:240]}")
    return details


def _query_stages() -> list[dict[str, str]]:
    return [
        {
            "query_name": GNOMAD_FULL_QUERY_NAME,
            "query_version": GNOMAD_FULL_QUERY_VERSION,
            "query_text": GNOMAD_FULL_QUERY,
        },
        {
            "query_name": GNOMAD_FREQUENCY_QUERY_NAME,
            "query_version": GNOMAD_FREQUENCY_QUERY_VERSION,
            "query_text": GNOMAD_FREQUENCY_QUERY,
        },
        {
            "query_name": GNOMAD_MINIMAL_QUERY_NAME,
            "query_version": GNOMAD_MINIMAL_QUERY_VERSION,
            "query_text": GNOMAD_MINIMAL_QUERY,
        },
    ]


def _attempt_from_exception(
    stage: dict[str, str],
    request_payload: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    error = _error_payload(exc)
    return {
        "query_name": stage["query_name"],
        "query_version": stage["query_version"],
        "outcome": "error",
        "endpoint": GNOMAD_GRAPHQL_ENDPOINT,
        "dataset": request_payload.get("variables", {}).get("dataset"),
        "variant_id": request_payload.get("variables", {}).get("variantId"),
        "request_payload_hash": raw_record_hash(request_payload),
        "http_status": error.get("status"),
        "error": error,
        "error_summary": _provider_error_summary(error),
    }


def _attempt_from_payload(
    stage: dict[str, str],
    request_payload: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    errors = payload.get("errors") if isinstance(payload, dict) else None
    variant_payload = ((payload.get("data") or {}).get("variant") if isinstance(payload, dict) else None)
    if errors:
        outcome = "no_record" if _is_variant_not_found_errors(errors) and variant_payload is None else "graphql_errors"
    elif variant_payload is None:
        outcome = "no_record"
    else:
        outcome = "success"
    return {
        "query_name": stage["query_name"],
        "query_version": stage["query_version"],
        "outcome": outcome,
        "endpoint": GNOMAD_GRAPHQL_ENDPOINT,
        "dataset": request_payload.get("variables", {}).get("dataset"),
        "variant_id": request_payload.get("variables", {}).get("variantId"),
        "request_payload_hash": raw_record_hash(request_payload),
        "graphql_errors": errors,
        "graphql_error_summary": _graphql_error_summary(errors) if errors else None,
        "payload": payload if errors else None,
    }


def _attempt_limitations(payload: dict[str, Any], *, include_failure_terms: bool = False) -> list[str]:
    limitations = []
    for attempt in payload.get("attempts") or []:
        if not isinstance(attempt, dict):
            continue
        outcome = attempt.get("outcome")
        if outcome not in {"error", "graphql_errors"}:
            continue
        summary = attempt.get("error_summary") or attempt.get("graphql_error_summary")
        prefix = "gnomAD query failed" if include_failure_terms else "gnomAD optional query returned an error"
        limitations.append(
            f"{prefix}: {attempt.get('query_name')} {attempt.get('query_version')} for {attempt.get('variant_id')} on {attempt.get('dataset')}: {summary}"
        )
        if attempt.get("http_status") is not None:
            limitations.append(f"gnomAD HTTP status: {attempt['http_status']}.")
        error = attempt.get("error") if isinstance(attempt.get("error"), dict) else {}
        if error.get("response_text"):
            limitations.append(f"gnomAD HTTP response body summary: {str(error['response_text'])[:240]}")
    return limitations


def _is_variant_not_found_payload(payload: dict[str, Any]) -> bool:
    errors = (payload.get("payload") or {}).get("errors")
    raw = (payload.get("payload") or {}).get("data", {}).get("variant")
    return raw is None and _is_variant_not_found_errors(errors)


def _is_variant_not_found_errors(errors: Any) -> bool:
    if not errors:
        return False
    summary = _graphql_error_summary(errors).lower()
    return "variant not found" in summary or "not found" == summary.strip()


def _provider_error_summary(payload: dict[str, Any]) -> str:
    parts = []
    if payload.get("status") is not None:
        parts.append(f"HTTP {payload['status']}")
    if payload.get("message"):
        parts.append(str(payload["message"]))
    if payload.get("response_text"):
        parts.append(str(payload["response_text"])[:240])
    return " | ".join(parts) or str(payload)[:240]
