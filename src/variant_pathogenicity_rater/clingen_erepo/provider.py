from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.clingen_erepo.draft import create_erepo_reviewed_evidence_drafts
from variant_pathogenicity_rater.clingen_erepo.matcher import evaluate_clingen_erepo_records
from variant_pathogenicity_rater.clingen_erepo.parser import parse_erepo_record
from variant_pathogenicity_rater.clingen_erepo.schema import (
    ClinGenERepoMatch,
    ClinGenERepoRecord,
    ERepoReviewedEvidenceDraft,
    VCEPSignal,
)
from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.evidence.clinvar import ClinVarRecord
from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


EREPO_REVIEW_NOTE = (
    "ClinGen Evidence Repository assertions are authoritative external review notes; "
    "they are not automatically applied ACMG evidence."
)


def clingen_erepo_candidate_evidence_id(record_id: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in record_id).strip("-")
    return f"ev-clingen-erepo-{safe[:48] or 'record'}"


class ClinGenERepoQuery(SchemaModel):
    gene: str | None = None
    ca_id: str | None = None
    clinvar_variation_id: str | None = None
    rsid: str | None = None
    hgvs_g: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    genomic_key: str | None = None
    condition: str | None = None
    transcript: str | None = None
    include_gene_signals: bool = True

    @classmethod
    def from_variant(
        cls,
        variant: Variant,
        context: GeneDiseaseContext | None = None,
        *,
        ca_id: str | None = None,
        clinvar_variation_id: str | None = None,
    ) -> "ClinGenERepoQuery":
        return cls(
            gene=variant.gene_symbol,
            ca_id=ca_id,
            clinvar_variation_id=clinvar_variation_id,
            hgvs_g=variant.hgvs_g,
            hgvs_c=variant.hgvs_c,
            hgvs_p=variant.hgvs_p,
            genomic_key=f"{variant.genome_build}:{variant.chrom.removeprefix('chr')}:{variant.pos}:{variant.ref.upper()}:{variant.alt.upper()}",
            condition=context.disease_name if context else None,
            transcript=variant.transcript.accession if variant.transcript else None,
        )

    def normalized_keys(self) -> set[str]:
        keys: set[str] = set()
        if self.gene and self.include_gene_signals:
            keys.add(f"gene:{self.gene.upper()}")
        if self.ca_id:
            keys.add(f"ca_id:{self.ca_id.upper().removeprefix('CA')}")
        if self.clinvar_variation_id:
            keys.add(f"variation_id:{self.clinvar_variation_id}")
        if self.rsid:
            keys.add(f"rsid:{self.rsid.lower().removeprefix('rs')}")
        if self.genomic_key:
            keys.add(f"genomic:{self.genomic_key.upper()}")
        if self.gene and self.hgvs_c:
            keys.add(f"gene_hgvs_c:{self.gene.upper()}:{self.hgvs_c.upper()}")
        if self.gene and self.hgvs_p:
            keys.add(f"gene_hgvs_p:{self.gene.upper()}:{self.hgvs_p.upper()}")
        return keys


class ClinGenERepoQueryResult(SchemaModel):
    query: ClinGenERepoQuery
    records: list[ClinGenERepoRecord] = Field(default_factory=list)
    matches: list[ClinGenERepoMatch] = Field(default_factory=list)
    vcep_signals: list[VCEPSignal] = Field(default_factory=list)
    reviewed_evidence_drafts: list[ERepoReviewedEvidenceDraft] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ClinGenERepoProvider(ABC):
    @abstractmethod
    def query(
        self,
        query: ClinGenERepoQuery,
        *,
        variant: Variant,
        context: GeneDiseaseContext,
        clinvar_records: list[ClinVarRecord] | None = None,
    ) -> ClinGenERepoQueryResult:
        raise NotImplementedError


def build_clingen_erepo_provider(
    config: DataSourceConfig,
    raw_records: list[dict[str, Any]] | None = None,
) -> ClinGenERepoProvider:
    if config.mode == ProviderMode.MOCK:
        return MockClinGenERepoProvider(raw_records)
    if config.mode == ProviderMode.LOCAL_FILE:
        return LocalFileClinGenERepoProvider(config)
    if config.mode == ProviderMode.ONLINE_DISABLED:
        return OnlineDisabledClinGenERepoProvider(config)
    if config.mode in {ProviderMode.ONLINE, ProviderMode.FUTURE_ONLINE}:
        return ClinGenERepoOnlineProvider(config)
    return OnlineDisabledClinGenERepoProvider(config)


class MockClinGenERepoProvider(ClinGenERepoProvider):
    def __init__(self, raw_records: list[dict[str, Any]] | None = None) -> None:
        self.raw_records = raw_records or MOCK_EREPO_RAW_RECORDS

    def query(
        self,
        query: ClinGenERepoQuery,
        *,
        variant: Variant,
        context: GeneDiseaseContext,
        clinvar_records: list[ClinVarRecord] | None = None,
    ) -> ClinGenERepoQueryResult:
        return _result_from_raw_records(
            raw_records=self.raw_records,
            query=query,
            variant=variant,
            context=context,
            clinvar_records=clinvar_records,
            base_limitations=[
                "ClinGen ERepo mock/local results are review notes only and not applied ACMG evidence.",
            ],
        )


class LocalFileClinGenERepoProvider(ClinGenERepoProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self.cache = DiskCache(config.cache_dir or ".cache/variant_pathogenicity_rater/clingen_erepo", config.ttl_seconds)

    def query(
        self,
        query: ClinGenERepoQuery,
        *,
        variant: Variant,
        context: GeneDiseaseContext,
        clinvar_records: list[ClinVarRecord] | None = None,
    ) -> ClinGenERepoQueryResult:
        query_payload = query.model_dump(mode="json", exclude_none=True)
        entry, _hit = self.cache.get_or_set(
            provider=self.config.name,
            mode=self.config.mode,
            source_version=self.config.source_version,
            query=query_payload,
            loader=lambda: _read_records(self.config),
            ttl_seconds=self.config.ttl_seconds,
        )
        return _result_from_raw_records(
            raw_records=entry.payload,
            query=query,
            variant=variant,
            context=context,
            clinvar_records=clinvar_records,
            base_limitations=[
                "ClinGen ERepo local-file source; source freshness depends on the supplied snapshot.",
                "ClinGen ERepo local-file mode is review-note only.",
                *self.config.limitations,
            ],
        )


class OnlineDisabledClinGenERepoProvider(ClinGenERepoProvider):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def query(
        self,
        query: ClinGenERepoQuery,
        *,
        variant: Variant,
        context: GeneDiseaseContext,
        clinvar_records: list[ClinVarRecord] | None = None,
    ) -> ClinGenERepoQueryResult:
        return ClinGenERepoQueryResult(
            query=query,
            limitations=[
                "ClinGen ERepo online provider is disabled by configuration.",
                "Provider disabled state was captured as a limitation; interpretation continued.",
            ],
        )


class ClinGenERepoOnlineProvider(ClinGenERepoProvider):
    SEARCH_ENDPOINT = "https://erepo.clinicalgenome.org/evrepo/api/classifications"

    def __init__(self, config: DataSourceConfig, *, http_get: Any | None = None) -> None:
        self.config = config
        self.cache = DiskCache(config.cache_dir or ".cache/variant_pathogenicity_rater/clingen_erepo", config.ttl_seconds)
        self.http_get = http_get or self._http_get

    def query(
        self,
        query: ClinGenERepoQuery,
        *,
        variant: Variant,
        context: GeneDiseaseContext,
        clinvar_records: list[ClinVarRecord] | None = None,
    ) -> ClinGenERepoQueryResult:
        if not self.config.online_enabled:
            return OnlineDisabledClinGenERepoProvider(self.config).query(
                query,
                variant=variant,
                context=context,
                clinvar_records=clinvar_records,
            )
        query_payload = query.model_dump(mode="json", exclude_none=True)
        try:
            entry, cache_hit = self.cache.get_or_set(
                provider=self.config.name,
                mode=self.config.mode,
                source_version=self.config.source_version or "ClinGen ERepo live",
                query=query_payload,
                loader=lambda: self._load_payload(query),
                ttl_seconds=self.config.ttl_seconds,
            )
            raw_records = _payload_records(entry.payload)
            result = _result_from_raw_records(
                raw_records=raw_records,
                query=query,
                variant=variant,
                context=context,
                clinvar_records=clinvar_records,
                base_limitations=[
                    "ClinGen ERepo online mode is opt-in and review-note only.",
                    *([] if not cache_hit else ["ClinGen ERepo response was served from cache."]),
                ],
            )
            result.provenance.append(
                {
                    "source": "ClinGen Evidence Repository",
                    "endpoint": self.SEARCH_ENDPOINT,
                    "retrieved_at": entry.created_at,
                    "cache_hit": cache_hit,
                    "query": query_payload,
                }
            )
            return result
        except Exception as exc:  # noqa: BLE001 - online failures must be limitations.
            return ClinGenERepoQueryResult(
                query=query,
                limitations=[
                    f"ClinGen ERepo online query failed: {exc.__class__.__name__}: {exc}",
                    "ClinGen ERepo online failure was captured as a limitation; interpretation continued.",
                    EREPO_REVIEW_NOTE,
                ],
            )

    def _load_payload(self, query: ClinGenERepoQuery) -> dict[str, Any]:
        params = {
            key: value
            for key, value in query.model_dump(mode="json", exclude_none=True).items()
            if key in {"gene", "ca_id", "clinvar_variation_id", "rsid", "hgvs_c", "hgvs_p", "condition"}
        }
        return {
            "endpoint": self.SEARCH_ENDPOINT,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "records": self.http_get(self.SEARCH_ENDPOINT, params),
        }

    def _http_get(self, endpoint: str, params: dict[str, str]) -> Any:
        url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.config.user_agent
                or "variant-pathogenicity-rater/0.1.0 (ClinGen ERepo optional online provider)"
            },
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def _result_from_raw_records(
    *,
    raw_records: list[dict[str, Any]],
    query: ClinGenERepoQuery,
    variant: Variant,
    context: GeneDiseaseContext,
    clinvar_records: list[ClinVarRecord] | None,
    base_limitations: list[str],
) -> ClinGenERepoQueryResult:
    query_payload = query.model_dump(mode="json", exclude_none=True)
    query_keys = query.normalized_keys()
    records = [
        parse_erepo_record(raw, query=query_payload)
        for raw in raw_records
        if query_keys.intersection(_record_keys(raw))
    ]
    matches, signals, review_flags, limitations = evaluate_clingen_erepo_records(
        variant=variant,
        context=context,
        records=records,
        query=query_payload,
        clinvar_records=clinvar_records,
    )
    drafts = create_erepo_reviewed_evidence_drafts(
        matches,
        {match.record.record_id: clingen_erepo_candidate_evidence_id(match.record.record_id) for match in matches},
    )
    provenance = [
        {
            "source": "ClinGen Evidence Repository",
            "record_id": record.record_id,
            "source_url": record.source_url,
            "api_endpoint": record.api_endpoint,
            "raw_snapshot_hash": record.raw_snapshot_hash,
            "classification_version": record.classification_version,
        }
        for record in records
    ]
    return ClinGenERepoQueryResult(
        query=query,
        records=records,
        matches=matches,
        vcep_signals=signals,
        reviewed_evidence_drafts=drafts,
        review_flags=review_flags,
        limitations=_unique(
            [
                *base_limitations,
                *limitations,
                *([] if records else ["No ClinGen ERepo record matched the supplied query."]),
                EREPO_REVIEW_NOTE,
            ]
        ),
        provenance=provenance,
    )


def _record_keys(raw: dict[str, Any]) -> set[str]:
    record = parse_erepo_record(raw)
    keys: set[str] = set()
    if record.gene:
        keys.add(f"gene:{record.gene.upper()}")
    if record.ca_id:
        keys.add(f"ca_id:{record.ca_id.upper().removeprefix('CA')}")
    if record.clinvar_variation_id:
        keys.add(f"variation_id:{record.clinvar_variation_id}")
    if record.rsid:
        keys.add(f"rsid:{record.rsid.lower().removeprefix('rs')}")
    if record.genomic_key:
        keys.add(f"genomic:{record.genomic_key.upper()}")
    if record.gene and record.hgvs_c:
        keys.add(f"gene_hgvs_c:{record.gene.upper()}:{record.hgvs_c.upper()}")
    if record.gene and record.hgvs_p:
        keys.add(f"gene_hgvs_p:{record.gene.upper()}:{record.hgvs_p.upper()}")
    return keys


def _read_records(config: DataSourceConfig) -> list[dict[str, Any]]:
    if not config.local_file:
        raise ValueError(f"{config.name} local_file mode requires a local_file path.")
    path = Path(config.local_file)
    if path.suffix.lower() in {".tsv", ".csv"}:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _payload_records(payload)


def _payload_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("records") or payload.get("data") or payload.get("classifications") or [payload]
    if not isinstance(payload, list):
        raise ValueError("ClinGen ERepo payload must be a list or records object.")
    return [record for record in payload if isinstance(record, dict)]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


MOCK_EREPO_RAW_RECORDS: list[dict[str, Any]] = [
    {
        "record_id": "erepo-brca1-68delag",
        "gene": "BRCA1",
        "ca_id": "CA000000001",
        "clinvar_variation_id": "17661",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "17",
            "position": 43092919,
            "ref": "AG",
            "alt": "A",
        },
        "disease_condition": "Hereditary breast and ovarian cancer",
        "vcep_name": "ClinGen Hereditary Breast, Ovarian and Pancreatic Cancer VCEP",
        "classification": "Pathogenic",
        "classification_date": "2025-01-15",
        "classification_version": "v1.0",
        "criteria_applied": [
            {"criterion": "PVS1", "strength": "very_strong", "direction": "pathogenic", "summary": "VCEP curated loss-of-function criterion."}
        ],
        "evidence_summaries": [
            {"summary_text": "ClinGen ERepo fixture exact match with VCEP supporting evidence summary.", "criteria_codes": ["PVS1"]}
        ],
        "citations": ["PMID:000000"],
        "source_url": "https://erepo.clinicalgenome.org/evrepo/uuid/erepo-brca1-68delag",
        "api_endpoint": "https://erepo.clinicalgenome.org/evrepo/api/classifications",
    }
]
