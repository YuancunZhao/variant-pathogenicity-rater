from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient
from variant_pathogenicity_rater.data_sources.provenance import raw_record_hash
from variant_pathogenicity_rater.literature_agent.query import build_query_plan
from variant_pathogenicity_rater.literature_agent.schema import LiteratureRecord, LiteratureSearchInput


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
LITVAR_SEARCH_URL = "https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/search"


def fetch_online_literature_records(
    request: LiteratureSearchInput,
    *,
    config: DataSourceConfig | None = None,
    http_client: Any | None = None,
) -> tuple[list[LiteratureRecord], list[str]]:
    config = config or DataSourceConfig(
        name="literature",
        mode=ProviderMode.ONLINE,
        online_enabled=True,
        source_version="PubMed/LitVar live",
        parser_version="literature-online-parser-v1",
    )
    if not config.online_enabled:
        return [], ["Online literature providers are disabled by default; no request was attempted."]
    client = http_client or ProviderHTTPClient(config)
    cache = DiskCache(config.cache_dir or ".cache/variant_pathogenicity_rater/literature")
    records: list[LiteratureRecord] = []
    limitations: list[str] = []
    if request.use_online_pubmed or request.use_online_search:
        pubmed, pubmed_limitations = _fetch_pubmed(request, config=config, http_client=client, cache=cache)
        records.extend(pubmed)
        limitations.extend(pubmed_limitations)
    if request.use_online_litvar or request.use_online_search:
        litvar, litvar_limitations = _fetch_litvar(request, config=config, http_client=client, cache=cache)
        records.extend(litvar)
        limitations.extend(litvar_limitations)
    return records, limitations


def _fetch_pubmed(
    request: LiteratureSearchInput,
    *,
    config: DataSourceConfig,
    http_client: Any,
    cache: DiskCache,
) -> tuple[list[LiteratureRecord], list[str]]:
    query = {
        "provider": "PubMed",
        "gene": request.gene,
        "variant": request.variant,
        "search_query": request.search_query,
        "pmids": request.pmids,
    }
    limitations = [
        "PubMed online records are literature search records only; no literature evidence is applied.",
    ]
    try:
        entry, cache_hit = cache.get_or_set(
            provider="pubmed",
            mode=str(config.mode),
            source_version=config.source_version or "PubMed EUtils live",
            query=query,
            loader=lambda: _load_pubmed_payload(request, config, http_client),
            ttl_seconds=config.ttl_seconds,
        )
        return _parse_pubmed_payload(entry.payload, request, config, cache_hit), limitations
    except Exception as exc:  # noqa: BLE001 - literature retrieval degrades.
        return [], [
            *limitations,
            f"PubMed online query failed: {exc.__class__.__name__}: {exc}",
            "PubMed failure was captured as a limitation; no literature evidence was applied.",
        ]


def _load_pubmed_payload(
    request: LiteratureSearchInput,
    config: DataSourceConfig,
    http_client: Any,
) -> dict[str, Any]:
    ids = list(request.pmids)
    if not ids:
        term = request.search_query or " OR ".join(item.query for item in build_query_plan(request)[:3])
        search = http_client.get_json(
            f"{EUTILS_BASE}/esearch.fcgi",
            {"db": "pubmed", "retmode": "json", "retmax": "20", "term": term, **_ncbi_identity(config)},
        )
        ids = [str(item) for item in search.get("esearchresult", {}).get("idlist", [])]
    summary = {}
    if ids:
        summary = http_client.get_json(
            f"{EUTILS_BASE}/esummary.fcgi",
            {
                "db": "pubmed",
                "retmode": "json",
                "id": ",".join(ids),
                **_ncbi_identity(config),
            },
        )
    return {
        "provider": "PubMedOnlineProvider",
        "source_version": config.source_version or "PubMed EUtils live",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": f"{EUTILS_BASE}/esummary.fcgi",
        "query": {
            "gene": request.gene,
            "variant": request.variant,
            "pmids": ids,
            "search_query": request.search_query,
        },
        "summary": summary,
    }


def _parse_pubmed_payload(
    payload: dict[str, Any],
    request: LiteratureSearchInput,
    config: DataSourceConfig,
    cache_hit: bool,
) -> list[LiteratureRecord]:
    result = payload.get("summary", {}).get("result", {})
    records: list[LiteratureRecord] = []
    for uid in result.get("uids") or []:
        raw = result.get(str(uid)) or {}
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or f"PubMed record {uid}")
        pubdate = str(raw.get("pubdate") or "")
        year = pubdate[:4] if pubdate[:4].isdigit() else None
        provenance = _record_provenance(payload, config, cache_hit, raw, "PubMed")
        records.append(
            LiteratureRecord(
                record_id=f"pubmed:{uid}",
                pmid=str(uid),
                title=title,
                abstract=None,
                source="PubMed",
                retrieval_timestamp=payload.get("retrieved_at"),
                query=payload.get("query"),
                matched_gene=request.gene,
                matched_variant=request.variant,
                matched_disease=request.disease,
                matched_transcript=request.transcript,
                variant_match_level="query_match",
                disease_match_level="query_match" if request.disease else None,
                study_type=str(raw.get("pubtype", ["unknown"])[0] if raw.get("pubtype") else "unknown"),
                evidence_domains=[],
                extracted_claims=[],
                citations=[f"PMID:{uid}", title],
                provenance=provenance,
                raw_record=raw,
            )
        )
    return records


def _fetch_litvar(
    request: LiteratureSearchInput,
    *,
    config: DataSourceConfig,
    http_client: Any,
    cache: DiskCache,
) -> tuple[list[LiteratureRecord], list[str]]:
    query = {
        "provider": "LitVar",
        "gene": request.gene,
        "variant": request.variant,
        "variant_aliases": request.variant_aliases,
    }
    limitations = [
        "LitVar online records are literature search records only; no literature evidence is applied.",
    ]
    try:
        entry, cache_hit = cache.get_or_set(
            provider="litvar",
            mode=str(config.mode),
            source_version=config.source_version or "LitVar live",
            query=query,
            loader=lambda: _load_litvar_payload(request, config, http_client),
            ttl_seconds=config.ttl_seconds,
        )
        return _parse_litvar_payload(entry.payload, request, config, cache_hit), limitations
    except Exception as exc:  # noqa: BLE001
        return [], [
            *limitations,
            f"LitVar online query failed: {exc.__class__.__name__}: {exc}",
            "LitVar failure was captured as a limitation; no literature evidence was applied.",
        ]


def _load_litvar_payload(
    request: LiteratureSearchInput,
    config: DataSourceConfig,
    http_client: Any,
) -> dict[str, Any]:
    query_text = " ".join([request.gene, request.variant, *(request.variant_aliases or [])]).strip()
    payload = http_client.get_json(LITVAR_SEARCH_URL, {"query": query_text})
    return {
        "provider": "LitVarOnlineProvider",
        "source_version": config.source_version or "LitVar live",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": LITVAR_SEARCH_URL,
        "query": {"query": query_text, "gene": request.gene, "variant": request.variant},
        "payload": payload,
    }


def _parse_litvar_payload(
    payload: dict[str, Any],
    request: LiteratureSearchInput,
    config: DataSourceConfig,
    cache_hit: bool,
) -> list[LiteratureRecord]:
    raw_records = payload.get("payload", {}).get("results") or payload.get("payload", {}).get("records") or []
    if isinstance(payload.get("payload"), list):
        raw_records = payload["payload"]
    records: list[LiteratureRecord] = []
    for index, raw in enumerate([item for item in raw_records if isinstance(item, dict)], start=1):
        pmid = raw.get("pmid") or raw.get("pmidList") or raw.get("pubmed_id")
        if isinstance(pmid, list):
            pmid = pmid[0] if pmid else None
        title = str(raw.get("title") or raw.get("article_title") or f"LitVar record {index}")
        abstract = raw.get("abstract")
        limitations = ["LitVar record has abstract-only evidence and requires manual review."] if abstract else []
        provenance = _record_provenance(payload, config, cache_hit, raw, "LitVar")
        if limitations:
            provenance["limitations"] = [*provenance.get("limitations", []), *limitations]
        records.append(
            LiteratureRecord(
                record_id=f"litvar:{pmid or index}",
                pmid=str(pmid) if pmid else None,
                title=title,
                abstract=str(abstract) if abstract else None,
                source="LitVar",
                retrieval_timestamp=payload.get("retrieved_at"),
                query=payload.get("query"),
                matched_gene=request.gene,
                matched_variant=request.variant,
                matched_disease=request.disease,
                matched_transcript=request.transcript,
                variant_match_level="query_match",
                disease_match_level="query_match" if request.disease else None,
                study_type=str(raw.get("publication_type") or "unknown"),
                evidence_domains=[],
                extracted_claims=[],
                citations=[item for item in [f"PMID:{pmid}" if pmid else None, title] if item],
                provenance=provenance,
                raw_record=raw,
            )
        )
    return records


def _record_provenance(
    payload: dict[str, Any],
    config: DataSourceConfig,
    cache_hit: bool,
    raw: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    return {
        "data_source": provider,
        "source_version": payload.get("source_version") or config.source_version,
        "retrieved_at": payload.get("retrieved_at"),
        "query": payload.get("query"),
        "endpoint": payload.get("endpoint"),
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/" if provider == "PubMed" else LITVAR_SEARCH_URL,
        "parser_version": config.parser_version,
        "raw_record_hash": raw_record_hash(raw),
        "cache_hit": cache_hit,
        "candidate_only": True,
        "applied": False,
        "limitations": [
            "Online literature record is caller/provider-supplied review material only.",
            "Manual review is required before any literature-derived criterion can be applied.",
        ],
    }


def _ncbi_identity(config: DataSourceConfig) -> dict[str, str]:
    return {"email": config.email} if config.email else {}
