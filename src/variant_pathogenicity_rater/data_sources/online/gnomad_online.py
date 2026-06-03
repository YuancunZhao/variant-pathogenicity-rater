from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient
from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.evidence.population import PopulationFrequencyProvider
from variant_pathogenicity_rater.schemas.evidence import EvidenceSource, PopulationFrequency
from variant_pathogenicity_rater.schemas.variant import Variant


GNOMAD_GRAPHQL_ENDPOINT = "https://gnomad.broadinstitute.org/api"
GNOMAD_QUERY = """
query Variant($variantId: String!, $dataset: DatasetId!) {
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
            return _empty_frequency(
                variant=variant,
                query=query,
                config=self.config,
                source_version=self._source_version(),
                raw_payload={
                    "provider": "gnomAD",
                    "query": query,
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
                limitations=[
                    f"gnomAD online query failed: {exc.__class__.__name__}: {exc}",
                    "gnomAD online failure was captured as a limitation; interpretation continued.",
                    "Provider failure is not evidence of population absence and cannot trigger PM2_Supporting.",
                ],
            )

    def _load_payload(self, query: dict[str, Any]) -> dict[str, Any]:
        payload = self.http_client.post_json(
            GNOMAD_GRAPHQL_ENDPOINT,
            {
                "query": GNOMAD_QUERY,
                "variables": {"variantId": query["variant_id"], "dataset": self.dataset},
            },
        )
        return {
            "provider": "GnomADOnlineProvider",
            "source_version": self._source_version(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": GNOMAD_GRAPHQL_ENDPOINT,
            "query": query,
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
    raw = (payload.get("payload") or {}).get("data", {}).get("variant")
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
    ]
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
        dataset="gnomAD",
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
