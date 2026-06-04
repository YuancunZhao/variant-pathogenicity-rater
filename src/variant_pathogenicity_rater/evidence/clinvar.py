from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from hashlib import sha1
from typing import Any

from pydantic import Field, model_validator

from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel
from variant_pathogenicity_rater.schemas.evidence import (
    ClinVarRecord,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import Variant


CLINVAR_PARSER_VERSION = "clinvar-parser-v2"
CLINVAR_REVIEW_NOTE = (
    "ClinVar assertions are treated as review notes by default. PP5/BP6 are not "
    "recommended for automatic use, and PS1/PM5 require independent variant-level assessment."
)
_UNKNOWN_DATE_VALUES = {"unknown", "not provided", "not_provided", "na", "n/a", "none", "null"}


class ClinVarQuery(SchemaModel):
    gene: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    rsid: str | None = None
    variation_id: str | None = None
    chromosome: str | None = None
    position: int | None = Field(default=None, ge=1)
    ref: str | None = None
    alt: str | None = None
    genome_build: str | None = None
    condition: str | None = None
    include_gene_comparators: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        aliases = {
            "gene_symbol": "gene",
            "rsID": "rsid",
            "clinvar_variation_id": "variation_id",
            "variationID": "variation_id",
            "chrom": "chromosome",
            "pos": "position",
        }
        for alias, target in aliases.items():
            if alias in normalized:
                value = normalized.pop(alias)
                normalized.setdefault(target, value)
        return normalized

    @classmethod
    def from_variant(cls, variant: Variant) -> ClinVarQuery:
        return cls(
            gene=variant.gene_symbol,
            hgvs_c=variant.hgvs_c,
            hgvs_p=variant.hgvs_p,
            chromosome=variant.chrom,
            position=variant.pos,
            ref=variant.ref,
            alt=variant.alt,
            genome_build=str(variant.genome_build),
        )

    def normalized_keys(self) -> set[str]:
        keys: set[str] = set()
        if self.gene and self.include_gene_comparators:
            keys.add(f"gene:{self.gene.upper()}")
        if self.gene and self.hgvs_c:
            keys.add(f"gene_hgvs_c:{self.gene.upper()}:{self.hgvs_c}")
        if self.gene and self.hgvs_p:
            keys.add(f"gene_hgvs_p:{self.gene.upper()}:{self.hgvs_p}")
        if self.rsid:
            keys.add(f"rsid:{self.rsid.lower().removeprefix('rs')}")
        if self.variation_id:
            keys.add(f"variation_id:{self.variation_id}")
        if self.chromosome and self.position and self.ref and self.alt:
            keys.add(
                "genomic:"
                f"{self.genome_build or 'GRCh38'}:"
                f"{self.chromosome.removeprefix('chr')}:"
                f"{self.position}:"
                f"{self.ref.upper()}:"
                f"{self.alt.upper()}"
            )
        return keys


class ClinVarQueryResult(SchemaModel):
    query: ClinVarQuery
    records: list[ClinVarRecord] = Field(default_factory=list)
    candidate_evidence_items: list[EvidenceItem] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ClinVarProvider(ABC):
    """Abstract ClinVar retrieval adapter.

    Providers retrieve source-specific records and delegate parsing/evidence mapping to
    the shared framework so MCP tools stay orchestration-only.
    """

    @abstractmethod
    def query(self, query: ClinVarQuery) -> ClinVarQueryResult:
        raise NotImplementedError


class MockClinVarProvider(ClinVarProvider):
    """Offline ClinVar provider with deterministic records for tests and demos."""

    def __init__(self, raw_records: list[dict[str, Any]] | None = None) -> None:
        self.raw_records = raw_records or MOCK_CLINVAR_RAW_RECORDS

    def query(self, query: ClinVarQuery) -> ClinVarQueryResult:
        query_keys = query.normalized_keys()
        records = [
            parse_clinvar_record(raw, query=query)
            for raw in self.raw_records
            if query_keys.intersection(_record_keys(raw))
        ]
        review_flags = _review_flags(records)
        return ClinVarQueryResult(
            query=query,
            records=records,
            candidate_evidence_items=[
                item
                for record in records
                for item in map_clinvar_record_to_candidate_evidence(record)
            ],
            review_flags=review_flags,
            limitations=_limitations(records),
        )


def parse_clinvar_record(
    raw_record: dict[str, Any], query: ClinVarQuery | None = None
) -> ClinVarRecord:
    source_payload = raw_record.get("source") or {}
    date_parse = _parse_clinvar_date(raw_record.get("last_evaluated"))
    provenance_limitations = [
        "ClinVar assertions are candidate review notes only; PP5/BP6 are disabled.",
        *date_parse["limitations"],
    ]
    source = EvidenceSource(
        name=source_payload.get("name", "ClinVar"),
        version=source_payload.get("version", "mock-clinvar-offline-v1"),
        url=source_payload.get("url", "https://www.ncbi.nlm.nih.gov/clinvar/"),
        database_id=str(raw_record["variation_id"]) if raw_record.get("variation_id") else None,
        retrieval_timestamp=source_payload.get("retrieved_at")
        or datetime.now(timezone.utc).isoformat(),
        query=query.model_dump(mode="json", exclude_none=True) if query else {},
        raw_snapshot_ref=source_payload.get("raw_snapshot_ref"),
    )
    provenance = provenance_from_raw_record(
        data_source=source.name,
        source_version=source.version,
        query=query.model_dump(mode="json", exclude_none=True) if query else {},
        raw_record=raw_record,
        source_url=source.url,
        endpoint=source_payload.get("endpoint"),
        provider_mode=source_payload.get("provider_mode"),
        cache_hit=source_payload.get("cache_hit"),
        request_method=source_payload.get("request_method"),
        request_url=source_payload.get("request_url"),
        raw_payload_kind=source_payload.get("raw_payload_kind"),
        retrieved_at=source_payload.get("retrieved_at"),
        review_status=raw_record.get("review_status"),
        last_evaluated=date_parse["normalized"],
        raw_last_evaluated=date_parse["raw"],
        last_evaluated_precision=date_parse["precision"],
        last_evaluated_parse_status=date_parse["status"],
        parser_version=source_payload.get("parser_version", CLINVAR_PARSER_VERSION),
        confidence=_confidence_from_raw(raw_record),
        limitations=provenance_limitations,
    )
    attach_provenance_to_source(source, provenance)
    conditions = list(raw_record.get("conditions") or [])
    condition = raw_record.get("condition") or ("; ".join(conditions) if conditions else None)
    genomic = raw_record.get("genomic") or {}
    hgvs_c = raw_record.get("hgvs_c") or (query.hgvs_c if query else None)
    hgvs_p = raw_record.get("hgvs_p") or (query.hgvs_p if query else None)
    return ClinVarRecord(
        source=source,
        variation_id=str(raw_record["variation_id"]) if raw_record.get("variation_id") else None,
        gene_symbol=raw_record.get("gene") or (query.gene if query else None),
        transcript=raw_record.get("transcript") or _transcript_from_hgvs_c(hgvs_c),
        hgvs_c=hgvs_c,
        hgvs_p=hgvs_p,
        protein_change=raw_record.get("protein_change") or hgvs_p,
        chromosome=raw_record.get("chromosome") or genomic.get("chromosome"),
        position=raw_record.get("position") or genomic.get("position"),
        ref=raw_record.get("ref") or genomic.get("ref"),
        alt=raw_record.get("alt") or genomic.get("alt"),
        genome_build=raw_record.get("genome_build") or genomic.get("genome_build"),
        clinical_significance=str(raw_record.get("clinical_significance", "not provided")),
        review_status=raw_record.get("review_status"),
        review_stars=_review_stars(raw_record.get("review_status")),
        review_confidence=_review_confidence(raw_record.get("review_status")),
        condition=condition,
        conditions=conditions,
        submitter_count=raw_record.get("submitter_count"),
        last_evaluated=date_parse["date"],
        conflicting_interpretations=bool(raw_record.get("conflicting_interpretations", False)),
        conflict_status=raw_record.get("conflict_status"),
        germline_or_somatic=raw_record.get("germline_or_somatic"),
        citations=[str(citation) for citation in raw_record.get("citations", [])],
    )


def map_clinvar_record_to_candidate_evidence(record: ClinVarRecord) -> list[EvidenceItem]:
    significance = record.clinical_significance.lower()
    if _is_somatic_only(record):
        return []
    if "conflicting" in significance or record.conflicting_interpretations:
        return [
            _candidate_item(
                record=record,
                code=EvidenceCode.PP5,
                direction=EvidenceDirection.CONFLICTING,
                reason="ClinVar reports conflicting interpretations; manual review is required.",
                candidate_codes=["PS1", "PM5", "PP5", "BP6"],
            )
        ]

    if _is_pathogenic_or_likely_pathogenic(significance):
        codes = ["PS1", "PM5", "PP5"] if _has_high_review_status(record.review_status) else ["PP5"]
        return [
            _candidate_item(
                record=record,
                code=EvidenceCode.PP5,
                direction=EvidenceDirection.PATHOGENIC,
                reason=(
                    "ClinVar has a pathogenic/likely pathogenic assertion. This is a candidate "
                    "review note only; do not auto-trigger PP5, PS1, or PM5."
                ),
                candidate_codes=codes,
            )
        ]

    if _is_benign_or_likely_benign(significance):
        return [
            _candidate_item(
                record=record,
                code=EvidenceCode.BP6,
                direction=EvidenceDirection.BENIGN,
                reason=(
                    "ClinVar has a benign/likely benign assertion. This is a candidate review "
                    "note only; do not auto-trigger BP6."
                ),
                candidate_codes=["BP6"],
            )
        ]

    return []


def _candidate_item(
    *,
    record: ClinVarRecord,
    code: EvidenceCode,
    direction: EvidenceDirection,
    reason: str,
    candidate_codes: list[str],
) -> EvidenceItem:
    digest = sha1(
        f"{record.source.name}:{record.variation_id}:{record.clinical_significance}:{code}".encode()
    ).hexdigest()
    return EvidenceItem(
        evidence_id=f"ev-clinvar-{digest[:12]}",
        code=code,
        strength=EvidenceStrength.NONE,
        direction=direction,
        reason=reason,
        source=record.source,
        confidence=0.5,
        requires_review=True,
        triggered_by=["clinvar_record"],
        supporting_data={
            "clinvar_record": record.model_dump(mode="json"),
            "candidate_acmg_codes": candidate_codes,
            "candidate_only": True,
            "evidence_status": "candidate",
            "applied": False,
            "automatic_application": False,
            "review_note": CLINVAR_REVIEW_NOTE,
        },
        review_flags=_review_flags([record]),
    )


def _review_flags(records: list[ClinVarRecord]) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    for record in records:
        significance = record.clinical_significance.lower()
        if record.conflicting_interpretations or "conflicting" in significance:
            flags.append(
                ReviewFlag(
                    code="CLINVAR_CONFLICTING_INTERPRETATIONS",
                    message=(
                        "ClinVar reports conflicting interpretations; manual review is required."
                    ),
                    severity="warning",
                    blocking=True,
                )
            )
        if record.germline_or_somatic and record.germline_or_somatic.lower() != "germline":
            flags.append(
                ReviewFlag(
                    code="CLINVAR_NON_GERMLINE_ASSERTION",
                    message=(
                        "ClinVar assertion is not clearly germline; assess applicability manually."
                    ),
                    severity="warning",
                    blocking=True,
                )
            )
        if _low_confidence_record(record):
            flags.append(
                ReviewFlag(
                    code="CLINVAR_LOW_REVIEW_CONFIDENCE",
                    message=(
                        "ClinVar assertion has low review confidence, single submitter, "
                        "or no assertion criteria."
                    ),
                    severity="warning",
                    blocking=False,
                )
            )
        if _old_submission(record):
            flags.append(
                ReviewFlag(
                    code="CLINVAR_OLD_SUBMISSION",
                    message="ClinVar assertion is older than five years; check current records.",
                    severity="warning",
                    blocking=False,
                )
            )
    return flags


def condition_review_flags(records: list[ClinVarRecord], query: ClinVarQuery) -> list[ReviewFlag]:
    if not query.condition:
        return []
    query_condition = query.condition.lower()
    flags: list[ReviewFlag] = []
    for record in records:
        record_conditions = [record.condition or "", *record.conditions]
        if record_conditions and not any(
            _condition_terms_overlap(query_condition, condition.lower())
            for condition in record_conditions
            if condition
        ):
            flags.append(
                ReviewFlag(
                    code="CLINVAR_CONDITION_MISMATCH",
                    message=(
                        "ClinVar condition does not clearly match the requested disease context."
                    ),
                    severity="warning",
                    blocking=True,
                )
            )
    return flags


def _limitations(records: list[ClinVarRecord]) -> list[str]:
    limitations = [
        "Offline mock ClinVar provider only; no network lookup was performed.",
        "ClinVar assertions are not final ACMG criteria and require qualified human review.",
        (
            "PP5 and BP6 are not recommended for automatic use; this framework emits "
            "review notes by default."
        ),
        "PS1 and PM5 require independent sequence/protein-level comparison before use.",
    ]
    if not records:
        limitations.append("No mock ClinVar record matched the supplied query.")
    limitations.extend(_record_provenance_limitations(records))
    return limitations


def clinvar_limitations(
    records: list[ClinVarRecord],
    *,
    offline: bool,
    cache_hit: bool | None = None,
) -> list[str]:
    limitations = [
        "ClinVar assertions are not final ACMG criteria and require qualified human review.",
        (
            "PP5 and BP6 are not recommended for automatic use; this framework emits "
            "review notes by default."
        ),
        "PS1 and PM5 require independent sequence/protein-level comparison before use.",
    ]
    if offline:
        limitations.insert(0, "Offline mock ClinVar provider only; no network lookup was performed.")
    else:
        limitations.insert(0, "ClinVar online mode is candidate-only; no ACMG criterion is auto-applied.")
        if cache_hit is True:
            limitations.append("ClinVar online result was served from disk cache.")
        elif cache_hit is False:
            limitations.append("ClinVar online result was retrieved and written to disk cache.")
    if any(_is_somatic_only(record) for record in records):
        limitations.append("Somatic-only ClinVar records were not used as germline ACMG candidates.")
    if not records:
        limitations.append("No ClinVar record matched the supplied query.")
    limitations.extend(_record_provenance_limitations(records))
    return limitations


def clinvar_record_parser_limitations(records: list[ClinVarRecord]) -> list[str]:
    return _record_provenance_limitations(records)


def _record_keys(raw_record: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    gene = raw_record.get("gene")
    if gene:
        keys.add(f"gene:{str(gene).upper()}")
    if gene and raw_record.get("hgvs_c"):
        keys.add(f"gene_hgvs_c:{str(gene).upper()}:{raw_record['hgvs_c']}")
    if gene and raw_record.get("hgvs_p"):
        keys.add(f"gene_hgvs_p:{str(gene).upper()}:{raw_record['hgvs_p']}")
    if raw_record.get("rsid"):
        keys.add(f"rsid:{str(raw_record['rsid']).lower().removeprefix('rs')}")
    if raw_record.get("variation_id"):
        keys.add(f"variation_id:{raw_record['variation_id']}")
    genomic = raw_record.get("genomic") or {}
    if genomic:
        keys.add(
            "genomic:"
            f"{genomic.get('genome_build', 'GRCh38')}:"
            f"{str(genomic['chromosome']).removeprefix('chr')}:"
            f"{genomic['position']}:"
            f"{str(genomic['ref']).upper()}:"
            f"{str(genomic['alt']).upper()}"
        )
    return keys


def _transcript_from_hgvs_c(value: str | None) -> str | None:
    if not value or ":" not in value:
        return None
    return value.split(":", 1)[0]


def _parse_clinvar_date(value: Any) -> dict[str, Any]:
    if value is None:
        return {
            "date": None,
            "normalized": None,
            "raw": None,
            "precision": None,
            "status": "missing",
            "limitations": [],
        }
    if isinstance(value, datetime):
        parsed = value.date()
        return {
            "date": parsed,
            "normalized": parsed.isoformat(),
            "raw": value.isoformat(),
            "precision": "day",
            "status": "parsed",
            "limitations": [],
        }
    if isinstance(value, date):
        return {
            "date": value,
            "normalized": value.isoformat(),
            "raw": value.isoformat(),
            "precision": "day",
            "status": "parsed",
            "limitations": [],
        }

    raw = str(value).strip()
    if not raw:
        return {
            "date": None,
            "normalized": None,
            "raw": raw,
            "precision": None,
            "status": "missing",
            "limitations": [],
        }
    if raw.lower() in _UNKNOWN_DATE_VALUES:
        return {
            "date": None,
            "normalized": None,
            "raw": raw,
            "precision": "unknown",
            "status": "unknown",
            "limitations": [f"ClinVar last_evaluated date was not provided: {raw!r}."],
        }
    if raw.isdigit() and len(raw) == 4:
        parsed = date(int(raw), 1, 1)
        return {
            "date": parsed,
            "normalized": parsed.isoformat(),
            "raw": raw,
            "precision": "year",
            "status": "parsed",
            "limitations": [
                "ClinVar last_evaluated date has year-only precision; normalized to "
                f"{parsed.isoformat()} for stable date handling."
            ],
        }

    normalized = raw.replace("/", "-").replace(".", "-")
    for candidate in (normalized[:10], raw[:10]):
        try:
            parsed = date.fromisoformat(candidate)
            return {
                "date": parsed,
                "normalized": parsed.isoformat(),
                "raw": raw,
                "precision": "day",
                "status": "parsed",
                "limitations": [],
            }
        except ValueError:
            pass

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            return {
                "date": parsed,
                "normalized": parsed.isoformat(),
                "raw": raw,
                "precision": "day",
                "status": "parsed",
                "limitations": [],
            }
        except ValueError:
            pass

    return {
        "date": None,
        "normalized": None,
        "raw": raw,
        "precision": "unparseable",
        "status": "unparseable",
        "limitations": [f"ClinVar last_evaluated date could not be parsed: {raw!r}."],
    }


def _record_provenance_limitations(records: list[ClinVarRecord]) -> list[str]:
    limitations: list[str] = []
    for record in records:
        provenance = getattr(record.source, "provenance", None)
        for limitation in getattr(provenance, "limitations", []) or []:
            if limitation.startswith("ClinVar last_evaluated date"):
                limitations.append(limitation)
    return _unique_strings(limitations)


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _has_high_review_status(review_status: str | None) -> bool:
    if not review_status:
        return False
    status = review_status.lower()
    return (
        "reviewed by expert panel" in status
        or "practice guideline" in status
        or "multiple submitters" in status
    )


def _review_stars(review_status: str | None) -> int:
    if not review_status:
        return 0
    status = review_status.lower()
    if "no assertion criteria" in status or "no assertion provided" in status:
        return 0
    if "practice guideline" in status:
        return 4
    if "reviewed by expert panel" in status:
        return 3
    if "multiple submitters" in status and "no conflicts" in status:
        return 2
    if "criteria provided" in status:
        return 1
    return 0


def _review_confidence(review_status: str | None) -> str:
    stars = _review_stars(review_status)
    if stars >= 3:
        return "high"
    if stars == 2:
        return "moderate"
    if stars == 1:
        return "low"
    return "very_low"


def _confidence_from_raw(raw_record: dict[str, Any]) -> float:
    review_status = raw_record.get("review_status")
    stars = _review_stars(review_status)
    if bool(raw_record.get("conflicting_interpretations", False)):
        return 0.2
    if stars >= 3:
        return 0.8
    if stars == 2:
        return 0.65
    if stars == 1:
        return 0.4
    return 0.25


def _low_confidence_record(record: ClinVarRecord) -> bool:
    status = (record.review_status or "").lower()
    return (
        "single submitter" in status
        or "no assertion criteria" in status
        or (record.review_stars is not None and record.review_stars <= 1)
        or (record.submitter_count == 1)
    )


def _old_submission(record: ClinVarRecord) -> bool:
    if record.last_evaluated is None:
        return False
    today = datetime.now(timezone.utc).date()
    return (today - record.last_evaluated).days > 5 * 365


def _is_somatic_only(record: ClinVarRecord) -> bool:
    value = (record.germline_or_somatic or "").lower()
    return "somatic" in value and "germline" not in value


def _condition_terms_overlap(query_condition: str, record_condition: str) -> bool:
    query_terms = {
        term
        for term in query_condition.replace("-", " ").replace("/", " ").split()
        if len(term) >= 4
    }
    record_terms = {
        term
        for term in record_condition.replace("-", " ").replace("/", " ").split()
        if len(term) >= 4
    }
    return bool(query_terms.intersection(record_terms))


def _is_pathogenic_or_likely_pathogenic(significance: str) -> bool:
    return (
        ("pathogenic" in significance or "likely pathogenic" in significance)
        and "benign" not in significance
    )


def _is_benign_or_likely_benign(significance: str) -> bool:
    return "benign" in significance and "pathogenic" not in significance


MOCK_CLINVAR_RAW_RECORDS: list[dict[str, Any]] = [
    {
        "variation_id": "17661",
        "gene": "BRCA1",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "rsid": "rs80357914",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "17",
            "position": 43124027,
            "ref": "AG",
            "alt": "A",
        },
        "clinical_significance": "Pathogenic",
        "review_status": "reviewed by expert panel",
        "conditions": ["Hereditary breast ovarian cancer syndrome"],
        "submitter_count": 12,
        "last_evaluated": "2025-04-01",
        "conflicting_interpretations": False,
        "germline_or_somatic": "germline",
        "citations": ["PMID:20301425", "PMID:23108138"],
    },
    {
        "variation_id": "7108",
        "gene": "CFTR",
        "hgvs_c": "NM_000492.4:c.1521_1523delCTT",
        "hgvs_p": "NP_000483.3:p.Phe508del",
        "rsid": "rs113993960",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "7",
            "position": 117559593,
            "ref": "CTT",
            "alt": "C",
        },
        "clinical_significance": "Pathogenic",
        "review_status": "criteria provided, multiple submitters, no conflicts",
        "conditions": ["Cystic fibrosis"],
        "submitter_count": 48,
        "last_evaluated": "2025-02-10",
        "conflicting_interpretations": False,
        "germline_or_somatic": "germline",
        "citations": ["PMID:7529962"],
    },
    {
        "variation_id": "13961",
        "gene": "HBB",
        "hgvs_c": "NM_000518.5:c.20A>T",
        "hgvs_p": "NP_000509.1:p.Glu7Val",
        "rsid": "rs334",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "11",
            "position": 5227002,
            "ref": "A",
            "alt": "T",
        },
        "clinical_significance": "Conflicting interpretations of pathogenicity",
        "review_status": "criteria provided, conflicting interpretations",
        "conditions": ["Sickle cell anemia"],
        "submitter_count": 22,
        "last_evaluated": "2024-12-12",
        "conflicting_interpretations": True,
        "germline_or_somatic": "germline",
        "citations": ["PMID:25741868"],
    },
    {
        "variation_id": "55555",
        "gene": "GENE1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "hgvs_p": "NP_000001.1:p.Lys26Arg",
        "rsid": "rs55555",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "1",
            "position": 123,
            "ref": "A",
            "alt": "G",
        },
        "clinical_significance": "Likely benign",
        "review_status": "criteria provided, single submitter",
        "conditions": ["not specified"],
        "submitter_count": 1,
        "last_evaluated": "2025-01-20",
        "conflicting_interpretations": False,
        "germline_or_somatic": "germline",
        "citations": [],
    },
]
