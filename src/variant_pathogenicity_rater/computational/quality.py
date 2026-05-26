from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.computational.schema import PredictorCall, PredictorGroup
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.variant import Variant


def computational_quality_checks(
    *,
    variant: Variant,
    calls: list[PredictorCall],
    annotation: VariantAnnotation | None = None,
    context_consistency: ContextConsistency | None = None,
) -> list[dict[str, Any]]:
    has_missense_calls = any(call.group == PredictorGroup.MISSENSE for call in calls)
    has_structured_splice_context = any(
        call.group == PredictorGroup.SPLICE and call.genome_build for call in calls
    )
    return [
        _check("missense_variant_type", _is_missense(variant, annotation) or _small_snv_without_lof(variant, annotation, has_missense_calls), "Missense predictors require a missense consequence."),
        _check("splice_relevance", has_structured_splice_context or _is_splice_relevant(variant, annotation), "Splice predictors require splice-relevant context."),
        _check("context_consistency", not _major_context_conflict(context_consistency), "Context consistency has no major conflict."),
        _check("source_quality", _source_quality_adequate(calls), "Computational source quality/provenance is adequate."),
        _check("transcript_match", _transcripts_match(variant, calls), "Predictor transcripts match the query transcript when supplied."),
        _check("genome_build_match", _genome_builds_match(variant, calls), "Predictor genome builds match the query build when supplied."),
    ]


def _check(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _is_missense(variant: Variant, annotation: VariantAnnotation | None) -> bool:
    terms = _terms(variant, annotation)
    if any(term in terms for term in ("frameshift", "stop_gained", "nonsense", "cnv", "sv")):
        return False
    return any(term in terms for term in ("missense", "missense_variant")) or bool(
        variant.hgvs_p and "p." in variant.hgvs_p and not any(token in variant.hgvs_p.lower() for token in ("fs", "ter", "*"))
    )


def _small_snv_without_lof(
    variant: Variant,
    annotation: VariantAnnotation | None,
    has_missense_calls: bool,
) -> bool:
    terms = _terms(variant, annotation)
    if not has_missense_calls or str(variant.variant_type) != "snv":
        return False
    return not any(term in terms for term in ("frameshift", "stop_gained", "nonsense", "cnv", "sv"))


def _is_splice_relevant(variant: Variant, annotation: VariantAnnotation | None) -> bool:
    terms = _terms(variant, annotation)
    return bool(
        annotation and annotation.splice_region
        or any("splice" in term or "intron" in term for term in terms)
        or (variant.hgvs_c and any(token in variant.hgvs_c for token in ("+", "-")))
    )


def _terms(variant: Variant, annotation: VariantAnnotation | None) -> set[str]:
    values: list[str] = []
    if annotation:
        values.extend(annotation.consequence_terms)
        if annotation.consequence:
            values.append(annotation.consequence)
    if variant.transcript and variant.transcript.consequence:
        values.append(variant.transcript.consequence)
    if variant.hgvs_p:
        text = variant.hgvs_p.lower()
        if "fs" in text:
            values.append("frameshift")
        if "ter" in text or "*" in text:
            values.append("nonsense")
    return {value.lower() for value in values if value}


def _major_context_conflict(context_consistency: ContextConsistency | None) -> bool:
    return bool(context_consistency and context_consistency.conflicts)


def _source_quality_adequate(calls: list[PredictorCall]) -> bool:
    return bool(calls) and not all(call.candidate_only for call in calls)


def _transcripts_match(variant: Variant, calls: list[PredictorCall]) -> bool:
    if not variant.transcript:
        return True
    expected = {variant.transcript.accession}
    if variant.transcript.version:
        expected.add(f"{variant.transcript.accession}.{variant.transcript.version}")
    return all(not call.transcript or call.transcript in expected for call in calls)


def _genome_builds_match(variant: Variant, calls: list[PredictorCall]) -> bool:
    return all(not call.genome_build or call.genome_build.lower() == str(variant.genome_build).lower() for call in calls)
