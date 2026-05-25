from __future__ import annotations

import re
from typing import Any

from variant_pathogenicity_rater.pvs1.schema import ConsequenceAssessment
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.variant import Transcript, Variant, VariantType


LOF_TERMS = {
    "frameshift_variant",
    "stop_gained",
    "splice_acceptor_variant",
    "splice_donor_variant",
    "exon_loss_variant",
}
CANDIDATE_ONLY_TERMS = {"start_lost", "stop_lost", "splice_region_variant"}
NON_LOF_TERMS = {"missense_variant", "inframe_deletion", "inframe_insertion", "synonymous_variant"}


def parse_variant_consequence(
    variant: Variant,
    annotation: VariantAnnotation | None = None,
    transcript: Transcript | None = None,
    provider_data: dict[str, Any] | None = None,
) -> ConsequenceAssessment:
    terms = _terms(annotation, transcript)
    sources: list[str] = []
    limitations: list[str] = []
    if terms:
        sources.append("annotation")
    hgvs_c = _first(annotation.hgvs_c if annotation else None, transcript.hgvs_c if transcript else None, variant.hgvs_c)
    hgvs_p = _first(annotation.hgvs_p if annotation else None, transcript.hgvs_p if transcript else None, variant.hgvs_p)

    inferred: list[str] = []
    if detect_frameshift_from_hgvs(hgvs_c, hgvs_p):
        inferred.append("frameshift_variant")
        sources.append("hgvs")
    if detect_nonsense_from_hgvs(hgvs_c, hgvs_p):
        inferred.append("stop_gained")
        sources.append("hgvs")
    if detect_canonical_splice_from_hgvs(hgvs_c):
        inferred.append("splice_donor_variant")
        sources.append("hgvs")
    if detect_start_loss_from_hgvs(hgvs_c, hgvs_p):
        inferred.append("start_lost")
        sources.append("hgvs")
    if detect_stop_lost_from_hgvs(hgvs_c, hgvs_p):
        inferred.append("stop_lost")
        sources.append("hgvs")
    terms = _unique([*terms, *inferred])

    if not terms and _small_indel_frameshift_by_length(variant):
        terms.append("frameshift_variant")
        sources.append("allele_length")
        limitations.append("Frameshift inferred from allele length because explicit annotation was absent.")

    primary = _primary(terms)
    is_splice = primary in {"splice_acceptor_variant", "splice_donor_variant"} or "splice_region_variant" in terms
    assessment = ConsequenceAssessment(
        primary_consequence=primary,
        consequence_terms=terms,
        is_lof=detect_lof_consequence(terms),
        is_splice=is_splice,
        is_candidate_only_type=primary in CANDIDATE_ONLY_TERMS or "splice_region_variant" in terms,
        rescue_risk=detect_inframe_rescue_risk(variant, terms, provider_data),
        splice_uncertainty=detect_splice_consequence_uncertainty(terms, provider_data),
        detection_sources=_unique(sources),
        limitations=limitations,
    )
    if primary in {"start_lost", "stop_lost"}:
        assessment.limitations.append(f"{primary} is candidate-only by default.")
    if any(term in NON_LOF_TERMS for term in terms) and not assessment.is_lof:
        assessment.limitations.append("Missense, synonymous, and in-frame terms do not trigger PVS1.")
    return assessment


def detect_lof_consequence(terms: list[str]) -> bool:
    normalized = {term.lower() for term in terms}
    return bool(normalized & LOF_TERMS or normalized & CANDIDATE_ONLY_TERMS)


def detect_frameshift_from_hgvs(hgvs_c: str | None = None, hgvs_p: str | None = None) -> bool:
    text = _join(hgvs_c, hgvs_p)
    return bool(re.search(r"fs(?:ter|\*)?", text) or "frameshift" in text)


def detect_nonsense_from_hgvs(hgvs_c: str | None = None, hgvs_p: str | None = None) -> bool:
    text = _join(hgvs_c, hgvs_p)
    return bool("stop_gained" in text or re.search(r"p\.\(?[a-z]{3}\d+(?:ter|\*)", text))


def detect_canonical_splice_from_hgvs(hgvs_c: str | None = None) -> bool:
    text = (hgvs_c or "").lower()
    return bool(re.search(r"c\.[\w*+-]+(?:\+|-)[12](?:[a-z]>[a-z]|del|dup|ins)", text))


def detect_start_loss_from_hgvs(hgvs_c: str | None = None, hgvs_p: str | None = None) -> bool:
    text = _join(hgvs_c, hgvs_p)
    return "start_lost" in text or bool(re.search(r"p\.\(?met1", text))


def detect_stop_lost_from_hgvs(hgvs_c: str | None = None, hgvs_p: str | None = None) -> bool:
    text = _join(hgvs_c, hgvs_p)
    return "stop_lost" in text or bool(re.search(r"p\.\*?\d+(?:[a-z]{3}|ext)", text))


def detect_inframe_rescue_risk(
    variant: Variant,
    terms: list[str],
    provider_data: dict[str, Any] | None = None,
) -> bool:
    lowered = {term.lower() for term in terms}
    if lowered & {"inframe_deletion", "inframe_insertion"}:
        return True
    if (provider_data or {}).get("possible_inframe_rescue") is True:
        return True
    if variant.variant_type != VariantType.SNV and abs(len(variant.ref) - len(variant.alt)) % 3 == 0:
        return "frameshift_variant" not in lowered
    return False


def detect_splice_consequence_uncertainty(
    terms: list[str],
    provider_data: dict[str, Any] | None = None,
) -> bool:
    if (provider_data or {}).get("rna_evidence") is True:
        return False
    lowered = {term.lower() for term in terms}
    return bool(lowered & {"splice_acceptor_variant", "splice_donor_variant", "splice_region_variant"})


def _terms(annotation: VariantAnnotation | None, transcript: Transcript | None) -> list[str]:
    values: list[str] = []
    if annotation is not None:
        values.extend(annotation.consequence_terms)
        if annotation.consequence:
            values.extend(re.split(r"[,&| ]+", annotation.consequence))
        if annotation.splice_region:
            values.append("splice_region_variant")
    if transcript and transcript.consequence:
        values.extend(re.split(r"[,&| ]+", transcript.consequence))
    return _unique(term.strip().lower() for term in values if term and term.strip())


def _primary(terms: list[str]) -> str | None:
    order = [
        "splice_acceptor_variant",
        "splice_donor_variant",
        "start_lost",
        "stop_lost",
        "splice_region_variant",
        "frameshift_variant",
        "stop_gained",
        "exon_loss_variant",
    ]
    return next((term for term in order if term in terms), terms[0] if terms else None)


def _small_indel_frameshift_by_length(variant: Variant) -> bool:
    return variant.variant_type != VariantType.SNV and abs(len(variant.ref) - len(variant.alt)) % 3 != 0


def _first(*values: str | None) -> str | None:
    return next((value for value in values if value), None)


def _join(*values: str | None) -> str:
    return " ".join(value for value in values if value).lower()


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
