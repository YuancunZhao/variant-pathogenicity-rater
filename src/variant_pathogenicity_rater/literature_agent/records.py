from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.literature_agent.schema import (
    LiteratureRecord,
    LiteratureRecordNormalizationResult,
    LiteratureSearchInput,
)


def normalize_literature_records(
    raw_records: list[dict[str, Any]],
    request: LiteratureSearchInput,
) -> LiteratureRecordNormalizationResult:
    records: list[LiteratureRecord] = []
    limitations: list[str] = []
    review_flags: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            limitations.append(f"literature_records[{index}] was not an object and was skipped.")
            review_flags.append(_flag("LITERATURE_RECORD_MALFORMED", index=index))
            continue
        try:
            records.append(normalize_literature_record(raw, request, index=index))
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            limitations.append(
                "literature_records["
                f"{index}] could not be normalized: {exc.__class__.__name__}: {exc}"
            )
            review_flags.append(_flag("LITERATURE_RECORD_MALFORMED", index=index))
    return LiteratureRecordNormalizationResult(
        records=records,
        limitations=limitations,
        review_flags=review_flags,
    )


def normalize_literature_record(
    raw: dict[str, Any],
    request: LiteratureSearchInput,
    *,
    index: int,
) -> LiteratureRecord:
    title = _first(raw, "title", "article_title", "name")
    abstract = _first(raw, "abstract", "summary", "snippet")
    full_text_excerpt = _first(raw, "full_text_excerpt", "excerpt", "text_excerpt")
    if not title:
        if abstract or full_text_excerpt:
            title = f"Untitled literature record {index + 1}"
        else:
            raise ValueError("title or abstract/full_text_excerpt is required")

    pmid = _first(raw, "pmid", "PMID")
    doi = _first(raw, "doi", "DOI")
    study_id = _first(raw, "study_id", "study", "family_id", "cohort_id")
    record_id = _first(raw, "record_id", "id", "article_id") or _stable_record_id(raw, index)
    source = _source_name(raw)
    matched_gene = _first(raw, "matched_gene", "gene", "gene_symbol") or request.gene
    matched_variant = (
        _first(raw, "matched_variant", "variant", "hgvs_c", "hgvs_p", "protein_change")
        or request.variant
    )
    matched_disease = _first(raw, "matched_disease", "disease", "condition") or request.disease
    matched_transcript = _first(raw, "matched_transcript", "transcript") or request.transcript
    variant_match_level = _match_level(
        explicit=_first(raw, "variant_match_level"),
        observed=matched_variant,
        expected=request.variant,
        exact_values={request.variant, *request.variant_aliases},
        missing_default="not_provided",
    )
    disease_match_level = _match_level(
        explicit=_first(raw, "disease_match_level"),
        observed=matched_disease,
        expected=request.disease,
        exact_values={request.disease} if request.disease else set(),
        missing_default="not_provided",
    )
    claims = _claims(raw)
    citations = _citations(raw, pmid=pmid, doi=doi)
    evidence_domains = _evidence_domains(raw)
    provenance = _provenance(raw, source=source, index=index)
    raw_query = raw.get("query") if raw.get("query") not in ("", None) else request.search_query

    return LiteratureRecord(
        record_id=str(record_id),
        pmid=str(pmid) if pmid else None,
        doi=str(doi) if doi else None,
        title=str(title),
        abstract=str(abstract) if abstract else None,
        full_text_excerpt=str(full_text_excerpt) if full_text_excerpt else None,
        source=source,
        retrieval_timestamp=_first(raw, "retrieval_timestamp", "retrieved_at")
        or datetime.now(timezone.utc).isoformat(),
        query=raw_query,
        matched_gene=str(matched_gene) if matched_gene else None,
        matched_variant=str(matched_variant) if matched_variant else None,
        matched_disease=str(matched_disease) if matched_disease else None,
        matched_transcript=str(matched_transcript) if matched_transcript else None,
        variant_match_level=variant_match_level,
        disease_match_level=disease_match_level,
        study_id=str(study_id) if study_id else None,
        duplicate_study_group=_first(raw, "duplicate_study_group", "duplicate_group"),
        study_type=_first(raw, "study_type", "type", "evidence_type"),
        evidence_domains=evidence_domains,
        extracted_claims=claims,
        citations=citations,
        provenance=provenance,
        raw_record=raw,
    )


def record_to_assessment_payload(record: LiteratureRecord) -> dict[str, Any]:
    raw = dict(record.raw_record)
    raw.setdefault("record_id", record.record_id)
    raw.setdefault("pmid", record.pmid)
    raw.setdefault("doi", record.doi)
    raw.setdefault("title", record.title)
    raw.setdefault("abstract", record.abstract)
    raw["source"] = record.source
    raw.setdefault("variant_match_level", record.variant_match_level)
    raw.setdefault("disease_match_level", record.disease_match_level)
    raw.setdefault("citation", record.citations[0] if record.citations else None)
    raw.setdefault("extracted_claims", record.extracted_claims)
    raw.setdefault("claim", " ".join(record.extracted_claims) if record.extracted_claims else None)
    raw.setdefault("provenance", record.provenance)
    return {key: value for key, value in raw.items() if value is not None}


def _first(raw: dict[str, Any], *keys: str) -> str | None:
    lowered = {str(key).lower(): value for key, value in raw.items()}
    for key in keys:
        value = raw.get(key)
        if value is None:
            value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value)
    return None


def _source_name(raw: dict[str, Any]) -> str:
    source = raw.get("source")
    if isinstance(source, dict):
        return str(source.get("name") or source.get("source") or "caller_supplied_literature_record")
    if source not in (None, ""):
        return str(source)
    provenance = raw.get("provenance")
    if isinstance(provenance, dict) and provenance.get("source"):
        return str(provenance["source"])
    return "caller_supplied_literature_record"


def _match_level(
    *,
    explicit: str | None,
    observed: str | None,
    expected: str | None,
    exact_values: set[str | None],
    missing_default: str,
) -> str:
    if explicit:
        return explicit
    if not observed or not expected:
        return missing_default
    normalized_observed = observed.strip().lower()
    exact = {str(value).strip().lower() for value in exact_values if value}
    if normalized_observed in exact:
        return "exact"
    return "mismatch"


def _claims(raw: dict[str, Any]) -> list[str]:
    claims = raw.get("extracted_claims") or raw.get("claims") or raw.get("sentences")
    if isinstance(claims, list):
        output: list[str] = []
        for item in claims:
            if isinstance(item, dict):
                value = item.get("description") or item.get("claim") or item.get("text")
                if value:
                    output.append(str(value))
            elif item not in (None, ""):
                output.append(str(item))
        return output
    claim = raw.get("extracted_claim") or raw.get("claim") or raw.get("description") or raw.get("finding")
    return [str(claim)] if claim not in (None, "") else []


def _citations(raw: dict[str, Any], *, pmid: str | None, doi: str | None) -> list[str]:
    citations = raw.get("citations")
    output = [str(item) for item in citations] if isinstance(citations, list) else []
    citation = raw.get("citation")
    if citation not in (None, ""):
        output.append(str(citation))
    if pmid:
        output.append(f"PMID:{pmid}")
    if doi:
        output.append(f"DOI:{doi}")
    return list(dict.fromkeys(output))


def _evidence_domains(raw: dict[str, Any]) -> list[str]:
    domains = raw.get("evidence_domains")
    if isinstance(domains, list):
        return [str(item) for item in domains if item not in (None, "")]
    evidence_type = raw.get("evidence_type") or raw.get("type")
    return [str(evidence_type)] if evidence_type not in (None, "") else []


def _provenance(raw: dict[str, Any], *, source: str, index: int) -> dict[str, Any]:
    provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    return {
        "source": source,
        "input_index": index,
        "caller_supplied": True,
        "requires_manual_review": True,
        **provenance,
    }


def _stable_record_id(raw: dict[str, Any], index: int) -> str:
    identity = {
        "index": index,
        "pmid": raw.get("pmid") or raw.get("PMID"),
        "doi": raw.get("doi") or raw.get("DOI"),
        "title": raw.get("title"),
        "study_id": raw.get("study_id"),
    }
    digest = sha1(repr(sorted(identity.items())).encode()).hexdigest()[:12]
    return f"literature-record-{digest}"


def _flag(code: str, *, index: int) -> dict[str, Any]:
    return {
        "code": code,
        "message": f"Literature record {index} requires manual review.",
        "severity": "warning",
        "blocking": True,
        "input_index": index,
    }
