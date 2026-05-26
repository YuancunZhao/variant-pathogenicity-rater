from __future__ import annotations

from datetime import date
from typing import Any

from variant_pathogenicity_rater.data_sources.provenance import raw_record_hash
from variant_pathogenicity_rater.clingen_erepo.schema import (
    ClinGenERepoRecord,
    ERepoCriteriaSummary,
    ERepoEvidenceSummary,
)


def parse_erepo_record(raw: dict[str, Any], *, query: dict[str, Any] | None = None) -> ClinGenERepoRecord:
    identifiers = _identifiers(raw)
    source_url = _first_text(raw, "source_url", "url", "evidence_repository_url", "record_url")
    endpoint = _first_text(raw, "api_endpoint", "endpoint")
    provenance = dict(raw.get("provenance") or {})
    if query:
        provenance.setdefault("query", query)
    provenance.setdefault("parser", "clingen-erepo-parser-v1")
    provenance.setdefault("raw_snapshot_hash", raw_record_hash(raw))

    return ClinGenERepoRecord(
        record_id=str(_first(raw, "record_id", "id", "uuid", "classification_id", default=raw_record_hash(raw)[:16])),
        gene=_first_text(raw, "gene", "gene_symbol", "hgnc_symbol"),
        variant_identifiers=identifiers,
        ca_id=_first_text(raw, "ca_id", "canonical_allele_id", "canonicalAlleleId", "caid"),
        clinvar_variation_id=_first_text(
            raw,
            "clinvar_variation_id",
            "clinvarVariationId",
            "variation_id",
            "variationID",
        ),
        rsid=_first_text(raw, "rsid", "rsID", "dbsnp_id"),
        hgvs_g=_first_text(raw, "hgvs_g", "hgvs_genomic", "hgvsGenomic"),
        hgvs_c=_first_text(raw, "hgvs_c", "hgvs_coding", "hgvsCoding", "hgvsc"),
        hgvs_p=_first_text(raw, "hgvs_p", "hgvs_protein", "hgvsProtein", "hgvsp"),
        genomic_key=_genomic_key(raw),
        transcript=_first_text(raw, "transcript", "transcript_id", "transcriptId"),
        protein_change=_first_text(raw, "protein_change", "proteinChange", "amino_acid_change"),
        disease_condition=_first_text(raw, "disease_condition", "condition", "disease", "mondo_label"),
        disease_id=_first_text(raw, "disease_id", "condition_id", "mondo_id"),
        inheritance=_first_text(raw, "inheritance", "mode_of_inheritance"),
        vcep_name=_first_text(raw, "vcep_name", "vcep", "affiliation", "affiliation_name"),
        affiliation_id=_first_text(raw, "affiliation_id", "affiliationId"),
        classification=str(_first(raw, "classification", "clinical_significance", "assertion", default="not provided")),
        classification_date=_parse_date(_first(raw, "classification_date", "date", "last_evaluated")),
        classification_version=_first_text(raw, "classification_version", "version", "rule_version"),
        criteria_applied=_criteria(raw),
        evidence_summaries=_evidence_summaries(raw),
        citations=_string_list(_first(raw, "citations", "pmids", "publications", default=[])),
        source_url=source_url,
        api_endpoint=endpoint,
        raw_snapshot_hash=raw_record_hash(raw),
        provenance=provenance,
        limitations=_string_list(raw.get("limitations") or []),
    )


def _identifiers(raw: dict[str, Any]) -> dict[str, Any]:
    identifiers = dict(raw.get("variant_identifiers") or raw.get("identifiers") or {})
    for key in ("ca_id", "clinvar_variation_id", "rsid", "hgvs_g", "hgvs_c", "hgvs_p"):
        value = raw.get(key)
        if value:
            identifiers.setdefault(key, value)
    return identifiers


def _genomic_key(raw: dict[str, Any]) -> str | None:
    explicit = _first_text(raw, "genomic_key", "normalized_genomic_key")
    if explicit:
        return explicit
    genomic = raw.get("genomic") if isinstance(raw.get("genomic"), dict) else raw
    build = _first_text(genomic, "genome_build", "build", "assembly") or "GRCh38"
    chrom = _first_text(genomic, "chromosome", "chrom")
    pos = _first(genomic, "position", "pos")
    ref = _first_text(genomic, "ref", "reference_allele", "reference")
    alt = _first_text(genomic, "alt", "alternate_allele", "alternate")
    if chrom and pos and ref and alt:
        return f"{build}:{chrom.removeprefix('chr')}:{pos}:{ref.upper()}:{alt.upper()}"
    return None


def _criteria(raw: dict[str, Any]) -> list[ERepoCriteriaSummary]:
    values = raw.get("criteria_applied") or raw.get("criteria") or raw.get("acmg_criteria") or []
    if isinstance(values, str):
        values = [item.strip() for item in values.replace(";", ",").split(",") if item.strip()]
    criteria = []
    for value in values:
        if isinstance(value, str):
            criteria.append(ERepoCriteriaSummary(criterion=value))
        elif isinstance(value, dict):
            criteria.append(
                ERepoCriteriaSummary(
                    criterion=str(value.get("criterion") or value.get("code") or value.get("name")),
                    strength=value.get("strength"),
                    direction=value.get("direction"),
                    applied_by_vcep=bool(value.get("applied_by_vcep", True)),
                    summary=value.get("summary") or value.get("rationale"),
                    citations=_string_list(value.get("citations") or []),
                    limitations=_string_list(value.get("limitations") or []),
                )
            )
    return criteria


def _evidence_summaries(raw: dict[str, Any]) -> list[ERepoEvidenceSummary]:
    values = raw.get("evidence_summaries") or raw.get("evidence") or raw.get("summary") or []
    if isinstance(values, str):
        values = [{"summary_text": values}]
    summaries = []
    for index, value in enumerate(values):
        if isinstance(value, str):
            summaries.append(ERepoEvidenceSummary(summary_id=f"summary-{index+1}", summary_text=value))
        elif isinstance(value, dict):
            text = value.get("summary_text") or value.get("text") or value.get("summary")
            if text:
                summaries.append(
                    ERepoEvidenceSummary(
                        summary_id=value.get("summary_id") or value.get("id") or f"summary-{index+1}",
                        evidence_type=value.get("evidence_type") or value.get("type"),
                        summary_text=str(text),
                        direction=value.get("direction"),
                        criteria_codes=_string_list(value.get("criteria_codes") or value.get("criteria") or []),
                        citations=_string_list(value.get("citations") or []),
                        provenance=dict(value.get("provenance") or {}),
                        limitations=_string_list(value.get("limitations") or []),
                    )
                )
    return summaries


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _first(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return default


def _first_text(raw: dict[str, Any], *keys: str) -> str | None:
    value = _first(raw, *keys)
    return str(value).strip() if value not in (None, "") else None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]
