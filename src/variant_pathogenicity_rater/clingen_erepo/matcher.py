from __future__ import annotations

from datetime import date
from typing import Any

from variant_pathogenicity_rater.clingen_erepo.schema import (
    ClinGenERepoMatch,
    ClinGenERepoMatchLevel,
    ClinGenERepoRecord,
    VCEPSignal,
)
from variant_pathogenicity_rater.evidence.clinvar import ClinVarRecord
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


STALE_CLASSIFICATION_DAYS = 3 * 365


def evaluate_clingen_erepo_records(
    *,
    variant: Variant,
    context: GeneDiseaseContext,
    records: list[ClinGenERepoRecord],
    query: dict[str, Any] | None = None,
    clinvar_records: list[ClinVarRecord] | None = None,
) -> tuple[list[ClinGenERepoMatch], list[VCEPSignal], list[ReviewFlag], list[str]]:
    matches: list[ClinGenERepoMatch] = []
    signals_by_key: dict[tuple[str, str | None, str | None], VCEPSignal] = {}
    review_flags: list[ReviewFlag] = []
    limitations: list[str] = []

    for record in records:
        match = _match_record(variant, context, record, query or {})
        review_flags.extend(match.review_flags)
        limitations.extend(match.limitations)
        if match.match_level != ClinGenERepoMatchLevel.NO_MATCH or match.matched_identifiers:
            matches.append(match)
        if _same_gene(record.gene, variant.gene_symbol or context.gene_symbol):
            key = (
                (record.gene or context.gene_symbol).upper(),
                record.disease_condition,
                record.vcep_name,
            )
            signal = signals_by_key.setdefault(
                key,
                VCEPSignal(
                    gene=record.gene or context.gene_symbol,
                    disease_condition=record.disease_condition,
                    vcep_name=record.vcep_name,
                    record_count=0,
                    limitations=[
                        "Gene-level ClinGen VCEP activity does not mean this variant has a ClinGen classification.",
                        "VCEP activity does not activate disease-specific rules or alter ACMG classification.",
                    ],
                ),
            )
            signal.record_count += 1
            signal.source_records.append(record.record_id)

    if clinvar_records:
        for match in matches:
            flags = _clinvar_erepo_conflict_flags(match.record, clinvar_records)
            match.review_flags.extend(flags)
            review_flags.extend(flags)

    matches.sort(key=lambda item: _match_rank(item.match_level), reverse=True)
    if not matches and records:
        limitations.append("ClinGen ERepo records were available, but no variant-level match was identified.")
    return matches, list(signals_by_key.values()), _unique_flags(review_flags), _unique(limitations)


def _match_record(
    variant: Variant,
    context: GeneDiseaseContext,
    record: ClinGenERepoRecord,
    query: dict[str, Any],
) -> ClinGenERepoMatch:
    matched: list[str] = []
    limitations = list(record.limitations)
    flags: list[ReviewFlag] = []
    blocked: list[str] = []
    condition_match = _condition_match(record.disease_condition, context.disease_name)
    transcript_match = _transcript_match(record, variant)
    gene_match = _same_gene(record.gene, variant.gene_symbol or context.gene_symbol)

    ca_id = query.get("ca_id") or query.get("canonical_allele_id")
    if ca_id and record.ca_id and _norm_id(ca_id) == _norm_id(record.ca_id):
        matched.append("ca_id")
    elif query.get("clinvar_variation_id") and record.clinvar_variation_id and str(query["clinvar_variation_id"]) == str(record.clinvar_variation_id):
        matched.append("clinvar_variation_id")
    elif _genomic_key(variant) and record.genomic_key and _genomic_key(variant) == _normalize_genomic_key(record.genomic_key):
        matched.append("genomic_key")
    elif _hgvs_match(record, variant):
        matched.append("hgvs")
    elif record.hgvs_p and variant.hgvs_p and _norm_text(record.hgvs_p) == _norm_text(variant.hgvs_p):
        matched.append("protein")

    if condition_match is False and matched and matched[0] in {"ca_id", "clinvar_variation_id", "genomic_key", "hgvs"}:
        blocked.append("Condition mismatch blocks high-confidence ClinGen ERepo exact match.")
        flags.append(_flag("CLINGEN_EREPO_CONDITION_MISMATCH", blocked[-1], blocking=True))
    if transcript_match is False and matched and matched[0] in {"ca_id", "clinvar_variation_id", "genomic_key", "hgvs"}:
        flags.append(
            _flag(
                "CLINGEN_EREPO_TRANSCRIPT_MISMATCH",
                "ClinGen ERepo transcript differs from the rated transcript; manual review is required.",
            )
        )
    if not record.classification_date or not record.classification_version:
        flags.append(
            _flag(
                "CLINGEN_EREPO_STALE_OR_UNVERSIONED",
                "ClinGen ERepo classification date/version is missing or incomplete.",
            )
        )
        limitations.append("ERepo classification date/version is missing or incomplete.")
    elif (date.today() - record.classification_date).days > STALE_CLASSIFICATION_DAYS:
        flags.append(
            _flag(
                "CLINGEN_EREPO_STALE_OR_UNVERSIONED",
                "ClinGen ERepo classification is older than the configured staleness threshold.",
            )
        )
        limitations.append("ERepo classification is older than the configured staleness threshold.")
    if not record.source_url or not record.raw_snapshot_hash or not record.provenance:
        limitations.append("ERepo source URL, raw snapshot hash, or provenance is incomplete.")

    if not matched and gene_match:
        level = ClinGenERepoMatchLevel.SAME_GENE
        confidence = 0.25
    elif matched and matched[0] == "protein":
        level = ClinGenERepoMatchLevel.SAME_PROTEIN
        confidence = 0.45
        flags.append(
            _flag(
                "CLINGEN_EREPO_PROTEIN_ONLY_MATCH",
                "Protein-only ClinGen ERepo match is not an exact variant match.",
            )
        )
    elif matched and blocked:
        level = ClinGenERepoMatchLevel.NO_MATCH
        confidence = 0.3
    elif matched:
        level = ClinGenERepoMatchLevel.EXACT_VARIANT
        confidence = {"ca_id": 0.98, "clinvar_variation_id": 0.92, "genomic_key": 0.9, "hgvs": 0.82}.get(matched[0], 0.7)
    else:
        level = ClinGenERepoMatchLevel.NO_MATCH
        confidence = 0.0

    if condition_match is False:
        confidence = min(confidence, 0.3)
    if transcript_match is False:
        confidence = min(confidence, 0.75)
    if limitations:
        confidence = min(confidence, 0.85)

    return ClinGenERepoMatch(
        query_variant={
            "variant_id": variant.variant_id,
            "genomic_key": _genomic_key(variant),
            "gene": variant.gene_symbol,
            "hgvs_c": variant.hgvs_c,
            "hgvs_p": variant.hgvs_p,
            **query,
        },
        record=record,
        match_level=level,
        confidence=confidence,
        matched_identifiers=matched,
        blocked_reasons=blocked,
        review_flags=flags,
        limitations=_unique(limitations),
        condition_match=condition_match,
        transcript_match=transcript_match,
        gene_match=gene_match,
        protein_only_match=matched[:1] == ["protein"],
    )


def _clinvar_erepo_conflict_flags(
    record: ClinGenERepoRecord,
    clinvar_records: list[ClinVarRecord],
) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    erepo_direction = _classification_direction(record.classification)
    if erepo_direction == "neutral":
        return flags
    for clinvar in clinvar_records:
        clinvar_direction = _classification_direction(clinvar.clinical_significance)
        if clinvar_direction != "neutral" and clinvar_direction != erepo_direction:
            flags.append(
                _flag(
                    "CLINGEN_EREPO_CLINVAR_CONFLICT",
                    "ClinVar and ClinGen ERepo classifications conflict; manual review is required.",
                )
            )
    return flags


def _classification_direction(value: str) -> str:
    text = value.lower()
    if "benign" in text:
        return "benign"
    if "pathogenic" in text:
        return "pathogenic"
    return "neutral"


def _condition_match(record_condition: str | None, query_condition: str | None) -> bool | None:
    if not record_condition or not query_condition or query_condition == "not provided":
        return None
    record_tokens = _tokens(record_condition)
    query_tokens = _tokens(query_condition)
    return bool(record_tokens.intersection(query_tokens))


def _transcript_match(record: ClinGenERepoRecord, variant: Variant) -> bool | None:
    query_transcript = variant.transcript.accession if variant.transcript else None
    record_transcript = record.transcript or _transcript_from_hgvs(record.hgvs_c)
    if not query_transcript or not record_transcript:
        return None
    return query_transcript.split(".", 1)[0] == record_transcript.split(".", 1)[0]


def _hgvs_match(record: ClinGenERepoRecord, variant: Variant) -> bool:
    return bool(
        (record.hgvs_c and variant.hgvs_c and _norm_text(record.hgvs_c) == _norm_text(variant.hgvs_c))
        or (record.hgvs_g and variant.hgvs_g and _norm_text(record.hgvs_g) == _norm_text(variant.hgvs_g))
    )


def _same_gene(left: str | None, right: str | None) -> bool:
    return bool(left and right and left.upper() == right.upper())


def _genomic_key(variant: Variant) -> str:
    return f"{variant.genome_build}:{variant.chrom.removeprefix('chr')}:{variant.pos}:{variant.ref.upper()}:{variant.alt.upper()}"


def _normalize_genomic_key(value: str) -> str:
    pieces = value.replace(">", ":").split(":")
    if len(pieces) >= 5:
        return f"{pieces[0]}:{pieces[1].removeprefix('chr')}:{pieces[2]}:{pieces[3].upper()}:{pieces[4].upper()}"
    return value


def _transcript_from_hgvs(value: str | None) -> str | None:
    return value.split(":", 1)[0] if value and ":" in value else None


def _norm_text(value: str) -> str:
    return value.strip().upper()


def _norm_id(value: str) -> str:
    return value.strip().upper().removeprefix("CA")


def _tokens(value: str) -> set[str]:
    return {token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split() if len(token) > 2}


def _match_rank(level: ClinGenERepoMatchLevel) -> int:
    return {
        ClinGenERepoMatchLevel.EXACT_VARIANT: 4,
        ClinGenERepoMatchLevel.SAME_PROTEIN: 3,
        ClinGenERepoMatchLevel.SAME_GENE: 2,
        ClinGenERepoMatchLevel.NO_MATCH: 1,
    }[level]


def _flag(code: str, message: str, *, blocking: bool = False) -> ReviewFlag:
    return ReviewFlag(code=code, message=message, severity="warning", blocking=blocking)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _unique_flags(flags: list[ReviewFlag]) -> list[ReviewFlag]:
    seen: set[tuple[str, str]] = set()
    unique: list[ReviewFlag] = []
    for flag in flags:
        key = (flag.code, flag.message)
        if key not in seen:
            seen.add(key)
            unique.append(flag)
    return unique
