from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.evidence.clinvar import (
    ClinVarProvider,
    ClinVarQuery,
    ClinVarQueryResult,
    MockClinVarProvider,
    _record_keys as clinvar_record_keys,
    _review_flags as clinvar_review_flags,
    clinvar_limitations,
    condition_review_flags,
    map_clinvar_record_to_candidate_evidence,
    parse_clinvar_record,
)
from variant_pathogenicity_rater.evidence.computational import (
    ComputationalPredictionProvider,
    MockComputationalPredictionProvider,
)
from variant_pathogenicity_rater.computational.providers import parse_local_computational_record
from variant_pathogenicity_rater.evidence.literature import (
    LiteratureProvider,
    LiteratureQuery,
    MockLiteratureProvider,
    _deduplicate_records,
    _record_keys as literature_record_keys,
    parse_literature_record,
)
from variant_pathogenicity_rater.evidence.population import (
    MockPopulationFrequencyProvider,
    PopulationFrequencyProvider,
)
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceSource,
    LiteratureEvidence,
    PopulationFrequency,
    SplicePrediction,
)
from variant_pathogenicity_rater.schemas.variant import Variant


class ProviderDisabledError(RuntimeError):
    """Raised by disabled or not-yet-implemented online providers."""


def build_clinvar_provider(
    config: DataSourceConfig,
    raw_records: list[dict[str, Any]] | None = None,
) -> ClinVarProvider:
    if config.mode == ProviderMode.MOCK:
        return MockClinVarProvider(raw_records)
    if config.mode == ProviderMode.LOCAL_FILE:
        return LocalFileClinVarProvider(config)
    if config.mode == ProviderMode.ONLINE_DISABLED:
        return OnlineDisabledClinVarProvider(config)
    if config.mode in {ProviderMode.ONLINE, ProviderMode.FUTURE_ONLINE}:
        _require_online_enabled(config)
        return ClinVarOnlineProvider(config)
    return FutureOnlineClinVarProvider(config)


def build_population_provider(
    config: DataSourceConfig,
    fixtures: dict[str, PopulationFrequency] | None = None,
) -> PopulationFrequencyProvider:
    if config.mode == ProviderMode.MOCK:
        return MockPopulationFrequencyProvider(fixtures)
    if config.mode == ProviderMode.LOCAL_FILE:
        return LocalFilePopulationFrequencyProvider(config)
    if config.mode == ProviderMode.ONLINE_DISABLED:
        return OnlineDisabledPopulationFrequencyProvider(config)
    return FutureOnlinePopulationFrequencyProvider(config)


def build_literature_provider(
    config: DataSourceConfig,
    raw_records: list[dict[str, Any]] | None = None,
) -> LiteratureProvider:
    if config.mode == ProviderMode.MOCK:
        return MockLiteratureProvider(raw_records)
    if config.mode == ProviderMode.LOCAL_FILE:
        return LocalFileLiteratureProvider(config)
    if config.mode == ProviderMode.ONLINE_DISABLED:
        return OnlineDisabledLiteratureProvider(config)
    return FutureOnlineLiteratureProvider(config)


def build_computational_provider(
    config: DataSourceConfig,
    fixtures: dict[str, list[ComputationalPrediction]] | None = None,
) -> ComputationalPredictionProvider:
    if config.mode == ProviderMode.MOCK:
        return MockComputationalPredictionProvider(fixtures)
    if config.mode == ProviderMode.LOCAL_FILE:
        return LocalFileComputationalPredictionProvider(config)
    if config.mode == ProviderMode.ONLINE_DISABLED:
        return OnlineDisabledComputationalPredictionProvider(config)
    return FutureOnlineComputationalPredictionProvider(config)


class LocalFileClinVarProvider(ClinVarProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self.cache = _cache(config)

    def query(self, query: ClinVarQuery) -> ClinVarQueryResult:
        query_payload = query.model_dump(mode="json", exclude_none=True)
        entry, _hit = self.cache.get_or_set(
            provider=self.config.name,
            mode=self.config.mode,
            source_version=self.config.source_version,
            query=query_payload,
            loader=lambda: _read_json_records(self.config),
            ttl_seconds=self.config.ttl_seconds,
        )
        query_keys = query.normalized_keys()
        records = []
        for raw in entry.payload:
            if query_keys.intersection(clinvar_record_keys(raw)):
                provenance = provenance_from_raw_record(
                    data_source=self.config.name,
                    source_version=self.config.source_version,
                    query=query_payload,
                    raw_record=raw,
                    parser_version=self.config.parser_version,
                    confidence=0.6,
                    limitations=[
                        "Local-file source; source freshness depends on the file snapshot.",
                        *self.config.limitations,
                    ],
                )
                record = parse_clinvar_record(raw, query=query)
                attach_provenance_to_source(record.source, provenance)
                records.append(record)
        review_flags = [
            *condition_review_flags(records, query),
        ]
        return ClinVarQueryResult(
            query=query,
            records=records,
            candidate_evidence_items=[
                item for record in records for item in map_clinvar_record_to_candidate_evidence(record)
            ],
            review_flags=review_flags,
            limitations=[
                "ClinVar local-file mode is candidate-only; PP5/BP6 remain disabled.",
                *([] if records else ["No local ClinVar record matched the supplied query."]),
            ],
        )


class ClinVarOnlineProvider(ClinVarProvider):
    """Optional NCBI E-utilities ClinVar provider.

    Construction is guarded by `build_clinvar_provider`; direct instantiation still enforces the
    explicit online flag so tests and callers cannot accidentally enable networking.
    """

    EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(
        self,
        config: DataSourceConfig,
        *,
        http_get: Any | None = None,
    ) -> None:
        _require_online_enabled(config)
        self.config = config
        self.cache = _cache(config)
        self.http_get = http_get or self._http_get

    def query(self, query: ClinVarQuery) -> ClinVarQueryResult:
        query_payload = query.model_dump(mode="json", exclude_none=True)
        try:
            entry, cache_hit = self.cache.get_or_set(
                provider=self.config.name,
                mode=self.config.mode,
                source_version=self._source_version(),
                query=query_payload,
                loader=lambda: self._load_payload(query),
                ttl_seconds=self.config.ttl_seconds,
            )
            raw_records = _extract_clinvar_online_records(entry.payload, query)
            records = []
            for raw in raw_records:
                raw["source"] = {
                    **(raw.get("source") or {}),
                    "name": "ClinVar",
                    "version": self._source_version(),
                    "url": raw.get("source_url") or "https://www.ncbi.nlm.nih.gov/clinvar/",
                    "endpoint": raw.get("endpoint"),
                    "retrieved_at": entry.payload.get("retrieved_at") or entry.created_at,
                    "parser_version": self.config.parser_version,
                }
                records.append(parse_clinvar_record(raw, query=query))
            review_flags = [*condition_review_flags(records, query), *clinvar_review_flags(records)]
            return ClinVarQueryResult(
                query=query,
                records=records,
                candidate_evidence_items=[
                    item
                    for record in records
                    for item in map_clinvar_record_to_candidate_evidence(record)
                ],
                review_flags=review_flags,
                limitations=clinvar_limitations(records, offline=False, cache_hit=cache_hit),
            )
        except Exception as exc:  # noqa: BLE001 - online failures must not break interpretation.
            return ClinVarQueryResult(
                query=query,
                records=[],
                candidate_evidence_items=[],
                review_flags=[],
                limitations=[
                    f"ClinVar online query failed: {exc.__class__.__name__}: {exc}",
                    "ClinVar online failure was captured as a limitation; interpretation continued.",
                    "ClinVar assertions are candidate-only and never determine final classification alone.",
                ],
            )

    def _load_payload(self, query: ClinVarQuery) -> dict[str, Any]:
        endpoint_payloads: list[dict[str, Any]] = []
        if query.variation_id:
            endpoint_payloads.append(self._esummary([query.variation_id]))
        else:
            ids = self._esearch(query)
            if ids:
                endpoint_payloads.append(self._esummary(ids))
        return {
            "provider": "ClinVarOnlineProvider",
            "source_version": self._source_version(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "query": query.model_dump(mode="json", exclude_none=True),
            "endpoint_payloads": endpoint_payloads,
        }

    def _esearch(self, query: ClinVarQuery) -> list[str]:
        params = {
            "db": "clinvar",
            "retmode": "json",
            "retmax": "20",
            "term": _clinvar_search_term(query),
            **self._ncbi_identity_params(),
        }
        payload = self.http_get(f"{self.EUTILS_BASE}/esearch.fcgi", params)
        return [str(uid) for uid in payload.get("esearchresult", {}).get("idlist", [])]

    def _esummary(self, ids: list[str]) -> dict[str, Any]:
        params = {
            "db": "clinvar",
            "retmode": "json",
            "id": ",".join(ids),
            **self._ncbi_identity_params(),
        }
        payload = self.http_get(f"{self.EUTILS_BASE}/esummary.fcgi", params)
        payload.setdefault("endpoint", f"{self.EUTILS_BASE}/esummary.fcgi")
        return payload

    def _http_get(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        headers = {
            "User-Agent": self.config.user_agent
            or "variant-pathogenicity-rater/0.1.0 (ClinVar optional online provider)"
        }
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _ncbi_identity_params(self) -> dict[str, str]:
        return {"email": self.config.email} if self.config.email else {}

    def _source_version(self) -> str:
        return self.config.source_version or "NCBI ClinVar E-utilities live"


class LocalFileLiteratureProvider(LiteratureProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self.cache = _cache(config)

    def search(self, query: LiteratureQuery) -> list[LiteratureEvidence]:
        query_payload = query.model_dump(mode="json", exclude_none=True)
        entry, _hit = self.cache.get_or_set(
            provider=self.config.name,
            mode=self.config.mode,
            source_version=self.config.source_version,
            query=query_payload,
            loader=lambda: _read_json_records(self.config),
            ttl_seconds=self.config.ttl_seconds,
        )
        query_keys = query.normalized_keys()
        records = []
        for raw in entry.payload:
            if query_keys.intersection(literature_record_keys(raw)):
                provenance = provenance_from_raw_record(
                    data_source=self.config.name,
                    source_version=self.config.source_version,
                    query=query_payload,
                    raw_record=raw,
                    parser_version=self.config.parser_version,
                    confidence=0.5,
                    limitations=[
                        "Local-file literature source; extracted claims are candidate-only.",
                        *self.config.limitations,
                    ],
                )
                record = parse_literature_record(raw, query=query)
                attach_provenance_to_source(record.source, provenance)
                records.append(record)
        return _deduplicate_records(records)


class LocalFilePopulationFrequencyProvider(PopulationFrequencyProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self.cache = _cache(config)

    def query(self, variant: Variant) -> PopulationFrequency:
        query = _variant_query(variant)
        entry, _hit = self.cache.get_or_set(
            provider=self.config.name,
            mode=self.config.mode,
            source_version=self.config.source_version,
            query=query,
            loader=lambda: _read_json_records(self.config),
            ttl_seconds=self.config.ttl_seconds,
        )
        query_keys = _population_query_keys(variant)
        mismatched_build = False
        for raw in entry.payload:
            if not query_keys.intersection(_population_record_keys(raw)):
                continue
            if _genome_build_mismatch(raw, variant):
                mismatched_build = True
                continue
            return _parse_local_population_frequency(raw, variant, query, self.config)
        limitations = [
            "No local population record matched the supplied query; this must not be interpreted as absence from population datasets.",
            *self.config.limitations,
        ]
        if mismatched_build:
            limitations.insert(
                0,
                "A local population record matched variant alleles but used a different genome build.",
            )
        return _empty_population_frequency(
            variant=variant,
            query=query,
            config=self.config,
            limitations=limitations,
        )


class LocalFileComputationalPredictionProvider(ComputationalPredictionProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self.cache = _cache(config)

    def query(self, variant: Variant) -> list[ComputationalPrediction]:
        query = _variant_query(variant)
        entry, _hit = self.cache.get_or_set(
            provider=self.config.name,
            mode=self.config.mode,
            source_version=self.config.source_version,
            query=query,
            loader=lambda: _read_json_records(self.config),
            ttl_seconds=self.config.ttl_seconds,
        )
        predictions = []
        query_keys = _computational_query_keys(variant)
        for raw in entry.payload:
            matched_by_coordinates = bool(query_keys.intersection(_computational_record_keys(raw)))
            if raw.get("variant_id") != variant.variant_id and not matched_by_coordinates:
                continue
            if _looks_like_spliceai_record(raw):
                predictions.append(_parse_local_spliceai_prediction(raw, variant, query, self.config))
                continue
            payloads = raw.get("predictions") or []
            if payloads:
                for prediction_payload in payloads:
                    prediction = ComputationalPrediction.model_validate(prediction_payload)
                    provenance = provenance_from_raw_record(
                        data_source=self.config.name,
                        source_version=self.config.source_version,
                        query=query,
                        raw_record=prediction_payload,
                        parser_version=self.config.parser_version,
                        confidence=0.5,
                        limitations=[
                            "Local-file computational source; PP3/BP4 require context-aware review.",
                            *self.config.limitations,
                        ],
                    )
                    attach_provenance_to_source(prediction.source, provenance)
                    predictions.append(prediction)
                continue
            for prediction in parse_local_computational_record(raw, source_name=self.config.name):
                provenance = provenance_from_raw_record(
                    data_source=self.config.name,
                    source_version=self.config.source_version or prediction.source.version,
                    query=query,
                    raw_record=raw,
                    parser_version=self.config.parser_version,
                    confidence=0.5,
                    limitations=[
                        "Local-file computational source; PP3/BP4 require consensus and human review.",
                        *self.config.limitations,
                    ],
                )
                attach_provenance_to_source(prediction.source, provenance)
                predictions.append(prediction)
        return predictions


class OnlineDisabledClinVarProvider(ClinVarProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def query(self, query: ClinVarQuery) -> ClinVarQueryResult:
        raise ProviderDisabledError("ClinVar online provider is disabled by configuration.")


class OnlineDisabledPopulationFrequencyProvider(PopulationFrequencyProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def query(self, variant: Variant) -> PopulationFrequency:
        raise ProviderDisabledError("Population online provider is disabled by configuration.")


class OnlineDisabledLiteratureProvider(LiteratureProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def search(self, query: LiteratureQuery) -> list[LiteratureEvidence]:
        raise ProviderDisabledError("Literature online provider is disabled by configuration.")


class OnlineDisabledComputationalPredictionProvider(ComputationalPredictionProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def query(self, variant: Variant) -> list[ComputationalPrediction]:
        raise ProviderDisabledError("Computational online provider is disabled by configuration.")


class FutureOnlineClinVarProvider(OnlineDisabledClinVarProvider):
    def query(self, query: ClinVarQuery) -> ClinVarQueryResult:
        _require_online_enabled(self.config)
        return ClinVarOnlineProvider(self.config).query(query)


class FutureOnlinePopulationFrequencyProvider(OnlineDisabledPopulationFrequencyProvider):
    def query(self, variant: Variant) -> PopulationFrequency:
        _require_online_enabled(self.config)
        raise ProviderDisabledError("Population future_online provider is not implemented.")


class FutureOnlineLiteratureProvider(OnlineDisabledLiteratureProvider):
    def search(self, query: LiteratureQuery) -> list[LiteratureEvidence]:
        _require_online_enabled(self.config)
        raise ProviderDisabledError("Literature future_online provider is not implemented.")


class FutureOnlineComputationalPredictionProvider(OnlineDisabledComputationalPredictionProvider):
    def query(self, variant: Variant) -> list[ComputationalPrediction]:
        _require_online_enabled(self.config)
        raise ProviderDisabledError("Computational future_online provider is not implemented.")


def _cache(config: DataSourceConfig) -> DiskCache:
    return DiskCache(config.cache_dir or ".cache/variant_pathogenicity_rater", config.ttl_seconds)


def _read_json_records(config: DataSourceConfig) -> list[dict[str, Any]]:
    if not config.local_file:
        raise ValueError(f"{config.name} local_file mode requires a local_file path.")
    path = Path(config.local_file)
    if path.suffix.lower() == ".tsv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]
    if path.suffix.lower() == ".jsonl":
        records = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{config.name} local_file JSONL parse failed on line {line_number}: {exc.msg}"
                ) from exc
            if isinstance(payload, dict):
                records.append(payload)
        return records
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("records", [payload])
    if not isinstance(payload, list):
        raise ValueError(f"{config.name} local_file payload must be a list or records object.")
    return [record for record in payload if isinstance(record, dict)]


def _require_online_enabled(config: DataSourceConfig) -> None:
    if not config.online_enabled:
        raise ProviderDisabledError(
            f"{config.name} online mode requires explicit online_enabled=true."
        )


def _clinvar_search_term(query: ClinVarQuery) -> str:
    if query.gene and query.hgvs_c:
        return f"{query.gene}[gene] AND \"{query.hgvs_c}\""
    if query.gene and query.hgvs_p:
        return f"{query.gene}[gene] AND \"{query.hgvs_p}\""
    if query.rsid:
        return f"{query.rsid.removeprefix('rs')}[RS]"
    if query.chromosome and query.position and query.ref and query.alt:
        chromosome = query.chromosome.removeprefix("chr")
        build = query.genome_build or "GRCh38"
        return (
            f"{build} {chromosome}:{query.position} {query.ref}>{query.alt} "
            "AND single nucleotide variant"
        )
    raise ValueError(
        "ClinVar online query requires gene+HGVS, rsID, variation_id, "
        "or chromosome+position+ref+alt."
    )


def _extract_clinvar_online_records(payload: dict[str, Any], query: ClinVarQuery) -> list[dict[str, Any]]:
    if isinstance(payload.get("records"), list):
        return [record for record in payload["records"] if isinstance(record, dict)]

    records: list[dict[str, Any]] = []
    for endpoint_payload in payload.get("endpoint_payloads", []):
        if isinstance(endpoint_payload.get("records"), list):
            records.extend(
                record for record in endpoint_payload["records"] if isinstance(record, dict)
            )
            continue
        result = endpoint_payload.get("result") or {}
        uids = result.get("uids") or []
        for uid in uids:
            summary = result.get(str(uid)) or {}
            if summary:
                records.append(_parse_esummary_record(summary, str(uid), endpoint_payload, query))
    return records


def _parse_esummary_record(
    summary: dict[str, Any],
    uid: str,
    endpoint_payload: dict[str, Any],
    query: ClinVarQuery,
) -> dict[str, Any]:
    clinical = _first_dict(
        summary.get("clinical_significance"),
        summary.get("germline_classification"),
        summary.get("classification"),
    )
    clinical_significance = _first_text(
        summary.get("clinical_significance"),
        clinical.get("description"),
        clinical.get("clinical_significance"),
        summary.get("title"),
        default="not provided",
    )
    review_status = _first_text(
        clinical.get("review_status"),
        summary.get("review_status"),
        summary.get("review_status_description"),
    )
    conditions = _extract_conditions(summary)
    germline_or_somatic = _first_text(
        summary.get("germline_or_somatic"),
        summary.get("classification_type"),
        clinical.get("classification_type"),
        default="germline" if summary.get("germline_classification") else None,
    )
    conflict_status = _first_text(
        summary.get("conflict_status"),
        clinical.get("conflict_status"),
        clinical.get("conflicting_classification"),
    )
    return {
        "variation_id": str(
            summary.get("variation_id")
            or summary.get("variationid")
            or summary.get("uid")
            or uid
        ),
        "gene": query.gene,
        "hgvs_c": query.hgvs_c,
        "hgvs_p": query.hgvs_p,
        "rsid": query.rsid,
        "clinical_significance": clinical_significance,
        "review_status": review_status,
        "conditions": conditions,
        "submitter_count": _first_int(
            summary.get("submitter_count"),
            summary.get("number_submitters"),
            clinical.get("submitter_count"),
        ),
        "last_evaluated": _first_text(
            summary.get("last_evaluated"),
            clinical.get("last_evaluated"),
            clinical.get("date_last_evaluated"),
        ),
        "conflicting_interpretations": "conflicting" in clinical_significance.lower()
        or "conflict" in (conflict_status or "").lower(),
        "conflict_status": conflict_status,
        "germline_or_somatic": germline_or_somatic,
        "citations": _extract_citations(summary),
        "source_url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
        "endpoint": endpoint_payload.get("endpoint"),
        "source": {
            "name": "ClinVar",
            "version": endpoint_payload.get("source_version") or "NCBI ClinVar E-utilities live",
            "url": f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{uid}/",
            "endpoint": endpoint_payload.get("endpoint"),
        },
    }


def _extract_conditions(summary: dict[str, Any]) -> list[str]:
    conditions: list[str] = []
    for key in ("conditions", "condition", "trait_name", "trait_set"):
        value = summary.get(key)
        if isinstance(value, str):
            conditions.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    conditions.append(item)
                elif isinstance(item, dict):
                    text = _first_text(
                        item.get("trait_name"),
                        item.get("name"),
                        item.get("preferred_name"),
                    )
                    if text:
                        conditions.append(text)
        elif isinstance(value, dict):
            text = _first_text(value.get("trait_name"), value.get("name"), value.get("preferred_name"))
            if text:
                conditions.append(text)
    return list(dict.fromkeys(conditions))


def _extract_citations(summary: dict[str, Any]) -> list[str]:
    citations: list[str] = []
    for value in (summary.get("citations"), summary.get("citation"), summary.get("pubmed_ids")):
        if isinstance(value, str):
            citations.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str | int):
                    citations.append(f"PMID:{item}" if isinstance(item, int) else item)
                elif isinstance(item, dict):
                    pmid = item.get("pmid") or item.get("pubmed_id")
                    if pmid:
                        citations.append(f"PMID:{pmid}")
                    elif item.get("citation"):
                        citations.append(str(item["citation"]))
    return list(dict.fromkeys(citations))


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _first_text(*values: Any, default: str | None = None) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float):
            return str(value)
    return default


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _variant_query(variant: Variant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "genome_build": variant.genome_build,
        "chrom": variant.chrom,
        "pos": variant.pos,
        "ref": variant.ref,
        "alt": variant.alt,
        "gene": variant.gene_symbol,
        "hgvs_c": variant.hgvs_c,
        "hgvs_p": variant.hgvs_p,
    }


def _parse_local_population_frequency(
    raw: dict[str, Any],
    variant: Variant,
    query: dict[str, Any],
    config: DataSourceConfig,
) -> PopulationFrequency:
    limitations = [
        "Local-file population source; PM2/BA1/BS1 still require disease context.",
        *config.limitations,
    ]
    try:
        payload = _population_payload(raw, variant, config, limitations)
        frequency = PopulationFrequency.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - malformed local data becomes a limitation.
        limitations.append(
            f"Matched local population record could not be parsed: {exc.__class__.__name__}: {exc}"
        )
        frequency = _empty_population_frequency(
            variant=variant,
            query=query,
            config=config,
            limitations=limitations,
            raw_record=raw,
        )
    provenance = provenance_from_raw_record(
        data_source=config.name,
        source_version=config.source_version or frequency.dataset_version or frequency.data_version,
        query=query,
        raw_record=raw,
        parser_version=config.parser_version,
        confidence=0.6 if not frequency.limitations else 0.4,
        limitations=frequency.limitations or limitations,
        ancestry=raw.get("ancestry") or raw.get("population"),
        population=frequency.population_name,
        allele_number=frequency.allele_number,
        coverage_quality=frequency.coverage_quality,
    )
    source = frequency.source or EvidenceSource(
        name=config.name,
        version=config.source_version or frequency.dataset_version or frequency.data_version,
        query=query,
    )
    attach_provenance_to_source(source, provenance)
    frequency.source = source
    return frequency


def _population_payload(
    raw: dict[str, Any],
    variant: Variant,
    config: DataSourceConfig,
    limitations: list[str],
) -> dict[str, Any]:
    population_name = _first_text(
        raw.get("population_name"),
        raw.get("population"),
        raw.get("ancestry"),
        default="global",
    )
    dataset_version = _first_text(raw.get("dataset_version"), raw.get("data_version"), config.source_version)
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    overall_af = _first_float(raw.get("overall_af"), raw.get("af"), raw.get("allele_frequency"))
    max_pop_af = _first_float(raw.get("max_pop_af"), raw.get("max_population_af"))
    allele_number = _first_int(raw.get("allele_number"), raw.get("an"))
    if overall_af is None and max_pop_af is None and allele_number is None:
        limitations.append("Matched local population record lacks usable AF and allele-number fields.")
    return {
        "source": {
            **source,
            "name": config.name,
            "version": dataset_version,
            "query": _variant_query(variant),
        },
        "overall_af": overall_af,
        "max_pop_af": max_pop_af,
        "population_name": population_name,
        "allele_count": _first_int(raw.get("allele_count"), raw.get("ac")),
        "allele_number": allele_number,
        "homozygote_count": _first_int(raw.get("homozygote_count"), raw.get("nhomalt")),
        "hemizygote_count": _first_int(raw.get("hemizygote_count"), raw.get("hemi_count")),
        "data_source": config.name,
        "filter_status": _first_text(raw.get("filter_status"), raw.get("filters")),
        "data_version": dataset_version,
        "is_absent": bool(raw.get("is_absent", False)),
        "faf95": _first_float(raw.get("faf95"), raw.get("faf_95")),
        "filtering_af": _first_float(raw.get("filtering_af"), raw.get("faf")),
        "genome_build": _first_text(raw.get("genome_build"), raw.get("build"), default=str(variant.genome_build)),
        "dataset_version": dataset_version,
        "coverage_quality": _first_text(raw.get("coverage_quality"), default="unknown"),
        "population_match": raw.get("population_match"),
        "limitations": limitations,
    }


def _empty_population_frequency(
    *,
    variant: Variant,
    query: dict[str, Any],
    config: DataSourceConfig,
    limitations: list[str],
    raw_record: dict[str, Any] | None = None,
) -> PopulationFrequency:
    source = EvidenceSource(
        name=config.name,
        version=config.source_version,
        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
    )
    provenance = provenance_from_raw_record(
        data_source=config.name,
        source_version=config.source_version,
        query=query,
        raw_record=raw_record or {"query": query, "provider": config.name, "matched": False},
        parser_version=config.parser_version,
        confidence=0.2,
        limitations=limitations,
    )
    attach_provenance_to_source(source, provenance)
    return PopulationFrequency(
        source=source,
        overall_af=None,
        max_pop_af=None,
        population_name="unknown",
        allele_count=None,
        allele_number=None,
        homozygote_count=None,
        hemizygote_count=None,
        data_source=config.name,
        data_version=config.source_version,
        is_absent=False,
        genome_build=str(variant.genome_build),
        dataset_version=config.source_version,
        coverage_quality="unknown",
        population_match=None,
        limitations=limitations,
    )


def _population_query_keys(variant: Variant) -> set[str]:
    keys = {
        variant.variant_id.lower(),
        _normalized_variant_key(variant.chrom, variant.pos, variant.ref, variant.alt),
    }
    if variant.gene_symbol and variant.hgvs_c:
        keys.add(f"{variant.gene_symbol.lower()}:{variant.hgvs_c.lower()}")
    if variant.gene_symbol and variant.hgvs_p:
        keys.add(f"{variant.gene_symbol.lower()}:{variant.hgvs_p.lower()}")
    return {key for key in keys if key}


def _population_record_keys(raw: dict[str, Any]) -> set[str]:
    chrom = _first_text(raw.get("chrom"), raw.get("chromosome"))
    pos = _first_int(raw.get("pos"), raw.get("position"))
    ref = _first_text(raw.get("ref"), raw.get("reference"))
    alt = _first_text(raw.get("alt"), raw.get("alternate"))
    gene = _first_text(raw.get("gene"), raw.get("gene_symbol"))
    keys = {str(raw.get("variant_id", "")).lower(), str(raw.get("variant_key", "")).lower()}
    if chrom and pos and ref and alt:
        keys.add(_normalized_variant_key(chrom, pos, ref, alt))
    for hgvs_key in ("hgvs_c", "hgvs_p"):
        hgvs = _first_text(raw.get(hgvs_key))
        if gene and hgvs:
            keys.add(f"{gene.lower()}:{hgvs.lower()}")
    return {key for key in keys if key}


def _computational_query_keys(variant: Variant) -> set[str]:
    keys = {
        variant.variant_id.lower(),
        _normalized_variant_key(variant.chrom, variant.pos, variant.ref, variant.alt),
    }
    return {key for key in keys if key}


def _computational_record_keys(raw: dict[str, Any]) -> set[str]:
    chrom = _first_text(raw.get("chrom"), raw.get("chromosome"), raw.get("#CHROM"))
    pos = _first_int(raw.get("pos"), raw.get("position"), raw.get("POS"))
    ref = _first_text(raw.get("ref"), raw.get("reference"), raw.get("REF"))
    alt = _first_text(raw.get("alt"), raw.get("alternate"), raw.get("ALT"))
    keys = {str(raw.get("variant_id", "")).lower(), str(raw.get("variant_key", "")).lower()}
    if chrom and pos and ref and alt:
        keys.add(_normalized_variant_key(chrom, pos, ref, alt))
    return {key for key in keys if key}


def _looks_like_spliceai_record(raw: dict[str, Any]) -> bool:
    keys = {key.lower() for key in raw}
    return bool(
        {"ds_ag", "ds_al", "ds_dg", "ds_dl"}.intersection(keys)
        or "max_delta_score" in keys
        or str(raw.get("method", "")).lower().replace("_", "").replace("-", "") == "spliceai"
    )


def _parse_local_spliceai_prediction(
    raw: dict[str, Any],
    variant: Variant,
    query: dict[str, Any],
    config: DataSourceConfig,
) -> ComputationalPrediction:
    ds_ag = _first_float(raw.get("DS_AG"), raw.get("ds_ag"))
    ds_al = _first_float(raw.get("DS_AL"), raw.get("ds_al"))
    ds_dg = _first_float(raw.get("DS_DG"), raw.get("ds_dg"))
    ds_dl = _first_float(raw.get("DS_DL"), raw.get("ds_dl"))
    max_delta_score = _first_float(raw.get("max_delta_score"), raw.get("MAX_DS"), raw.get("max_ds"))
    if max_delta_score is None:
        max_delta_score = max(value for value in (ds_ag, ds_al, ds_dg, ds_dl, 0.0) if value is not None)
    predicted_consequence = _first_text(
        raw.get("predicted_consequence"),
        raw.get("consequence"),
        raw.get("prediction"),
        default=_spliceai_consequence(max_delta_score),
    )
    source_version = _first_text(
        raw.get("source_version"),
        raw.get("SpliceAI_version"),
        raw.get("spliceai_version"),
        config.source_version,
    )
    genome_build = _first_text(raw.get("genome_build"), raw.get("build"))
    transcript = _first_text(raw.get("transcript"), raw.get("transcript_id"))
    affected_gene = _first_text(
        raw.get("affected_gene"),
        raw.get("gene"),
        raw.get("gene_symbol"),
        default=variant.gene_symbol or "unknown",
    )
    limitations = [
        "SpliceAI local-file source; computational evidence only.",
        "SpliceAI cannot trigger PS3, BS3, or PVS1 and does not override the PVS1 engine.",
        *config.limitations,
    ]
    candidate_only = bool(raw.get("candidate_only", False))
    if genome_build and genome_build.lower() != str(variant.genome_build).lower():
        candidate_only = True
        limitations.append(
            "SpliceAI record matched alleles but genome build differs from the query variant."
        )
    if _transcript_mismatch(transcript, variant):
        candidate_only = True
        limitations.append(
            "SpliceAI transcript differs from the query transcript; record is candidate-only."
        )
    source = EvidenceSource(
        name=_first_text(raw.get("source_name"), default=config.name) or config.name,
        version=source_version,
        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
        raw_snapshot_ref=_first_text(raw.get("raw_snapshot_ref")),
    )
    splice_prediction = SplicePrediction(
        source=source,
        DS_AG=ds_ag,
        DS_AL=ds_al,
        DS_DG=ds_dg,
        DS_DL=ds_dl,
        max_delta_score=max_delta_score,
        predicted_consequence=predicted_consequence or "uncertain",
        affected_gene=affected_gene or variant.gene_symbol or "unknown",
        transcript=transcript,
        source_version=source_version,
        genome_build=genome_build or str(variant.genome_build),
        candidate_only=candidate_only,
        limitations=limitations,
    )
    provenance = provenance_from_raw_record(
        data_source=config.name,
        source_version=source_version,
        query=query,
        raw_record=raw,
        parser_version=config.parser_version,
        confidence=0.4 if candidate_only else 0.6,
        limitations=limitations,
    )
    splice_prediction.provenance = provenance
    attach_provenance_to_source(source, provenance)
    return ComputationalPrediction(
        source=source,
        method="SpliceAI",
        score=max_delta_score,
        prediction=predicted_consequence or "uncertain",
        threshold=_first_float(raw.get("threshold")),
        transcript=transcript,
        candidate_only=candidate_only,
        limitations=limitations,
        splice_prediction=splice_prediction,
    )


def _spliceai_consequence(max_delta_score: float) -> str:
    if max_delta_score >= 0.5:
        return "splice altering"
    if max_delta_score <= 0.1:
        return "no predicted splice impact"
    return "uncertain splice impact"


def _transcript_mismatch(transcript: str | None, variant: Variant) -> bool:
    if not transcript or not variant.transcript:
        return False
    expected = {variant.transcript.accession}
    if variant.transcript.version:
        expected.add(f"{variant.transcript.accession}.{variant.transcript.version}")
    return transcript not in expected


def _normalized_variant_key(chrom: str, pos: int, ref: str, alt: str) -> str:
    normalized_chrom = chrom.removeprefix("chr").removeprefix("Chr").removeprefix("CHR")
    return f"{normalized_chrom}-{pos}-{ref}-{alt}".lower()


def _genome_build_mismatch(raw: dict[str, Any], variant: Variant) -> bool:
    record_build = _first_text(raw.get("genome_build"), raw.get("build"))
    return bool(record_build and record_build.lower() != str(variant.genome_build).lower())


def _first_float(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None
