from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.schemas.variant import (
    GeneDiseaseContext,
    GenomeBuild,
    LastExonInformation,
    Transcript,
    Variant,
    VariantType,
)
from variant_pathogenicity_rater.variant_resolution.coordinate_resolver import resolve_coordinate
from variant_pathogenicity_rater.variant_resolution.exon_resolver import resolve_exon_context
from variant_pathogenicity_rater.variant_resolution.nmd_context_resolver import resolve_nmd_context
from variant_pathogenicity_rater.variant_resolution.protein_resolver import resolve_protein
from variant_pathogenicity_rater.variant_resolution.provider import (
    find_resolution_record,
    load_resolution_records,
)
from variant_pathogenicity_rater.variant_resolution.safety import (
    can_apply_coordinate_to_variant,
    coordinate_conflicts,
    resolution_consistency_flags,
    unique_flags,
)
from variant_pathogenicity_rater.variant_resolution.schema import (
    ResolutionStep,
    VariantResolutionResult,
)
from variant_pathogenicity_rater.variant_resolution.transcript_resolver import resolve_transcript


def resolve_variant(
    variant: Variant | dict[str, Any],
    *,
    context: GeneDiseaseContext | None = None,
    options: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> VariantResolutionResult:
    if isinstance(variant, dict):
        from variant_pathogenicity_rater.normalization import normalize_variant

        normalization = normalize_variant(variant)
        if normalization.normalized_variant is None:
            return VariantResolutionResult(
                status="error",
                confidence=0.0,
                limitations=["Variant payload could not be normalized before resolution."],
            )
        variant = normalization.normalized_variant
    options = options or {}
    loaded_records, fixture_limitations = load_resolution_records(
        records if records is not None else options.get("transcript_resolution_records")
    )
    record = find_resolution_record(
        loaded_records,
        gene=variant.gene_symbol or (context.gene_symbol if context else None),
        hgvs_c=variant.hgvs_c,
        transcript=_variant_transcript(variant),
    )

    resolved_transcript = resolve_transcript(variant, record)
    resolved_protein = resolve_protein(variant, record)
    resolved_coordinate = resolve_coordinate(record, fallback_variant=variant)
    exon_context = resolve_exon_context(record)
    nmd_context = resolve_nmd_context(record, exon_context)

    flags = [
        *resolution_consistency_flags(variant, record, resolved_coordinate),
        *coordinate_conflicts(variant, resolved_coordinate),
    ]
    limitations = [
        *fixture_limitations,
        *resolved_transcript.limitations,
        *resolved_protein.limitations,
        *resolved_coordinate.limitations,
        *exon_context.limitations,
        *nmd_context.limitations,
    ]
    if record is None:
        limitations.append("No matching local transcript resolution fixture was found.")
    enriched_variant = _enriched_variant(
        variant,
        resolved_transcript=resolved_transcript,
        resolved_protein=resolved_protein,
        resolved_coordinate=resolved_coordinate,
        coordinate_flags=flags,
    )
    enriched_context = _enriched_context(
        context,
        variant,
        exon_context,
        nmd_context,
        preserve_manual_nmd_context=bool(options.get("preserve_manual_nmd_context")),
    )
    components = [
        resolved_transcript.confidence,
        resolved_protein.confidence,
        resolved_coordinate.confidence,
        exon_context.confidence,
        nmd_context.nmd_confidence,
    ]
    resolved_components = [value for value in components if value > 0]
    confidence = round(sum(resolved_components) / len(components), 2) if components else 0.0
    status = "unresolved"
    if len(resolved_components) == len(components):
        status = "resolved"
    elif resolved_components:
        status = "partial"

    provenance = []
    if record is not None:
        provenance.append(
            {
                "source": record.source,
                "source_version": record.source_version,
                "raw_snapshot_ref": record.raw_snapshot_ref,
                "scope": "variant resolution only; not ACMG evidence",
                **record.provenance,
            }
        )
    runtime = _resolution_runtime(record, confidence, status, limitations)
    return VariantResolutionResult(
        status=status,
        outcome=_outcome(status, record, limitations),
        confidence=confidence,
        resolved_transcript=resolved_transcript,
        resolved_hgvs_p=resolved_protein,
        resolved_coordinate=resolved_coordinate,
        exon_context=exon_context,
        nmd_context=nmd_context,
        limitations=_unique(limitations),
        review_flags=unique_flags(flags),
        resolution_steps=[
            _step("transcript_resolution", resolved_transcript.confidence),
            _step("protein_resolution", resolved_protein.confidence),
            _step("coordinate_resolution", resolved_coordinate.confidence),
            _step("exon_resolution", exon_context.confidence),
            _step("nmd_context_resolution", nmd_context.nmd_confidence),
        ],
        provenance=provenance,
        resolution_runtime=runtime,
        resolved_variant=enriched_variant,
        resolved_context=enriched_context,
    )


def _outcome(status: str, record: Any, limitations: list[str]) -> str:
    if any("failed" in item.lower() for item in limitations):
        return "failure"
    if status == "resolved":
        return "success"
    if status == "partial":
        return "partial"
    if record is None:
        return "no_record"
    return "skipped"


def _resolution_runtime(
    record: Any,
    confidence: float,
    status: str,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "provider": record.source if record is not None else "local_transcript_resolution_fixture",
        "outcome": _outcome(status, record, limitations),
        "source_version": record.source_version if record is not None else None,
        "cache_hit": None,
        "confidence": confidence,
        "limitations": _unique(limitations),
    }


def _enriched_variant(
    variant: Variant,
    *,
    resolved_transcript: Any,
    resolved_protein: Any,
    resolved_coordinate: Any,
    coordinate_flags: list[Any],
) -> Variant:
    update: dict[str, Any] = {}
    transcript = variant.transcript
    if transcript is not None:
        transcript_update: dict[str, Any] = {}
        if resolved_protein.hgvs_p and not transcript.hgvs_p:
            transcript_update["hgvs_p"] = resolved_protein.hgvs_p
        if resolved_protein.consequence and not transcript.consequence:
            transcript_update["consequence"] = resolved_protein.consequence
        if resolved_transcript.protein_accession:
            transcript_update["mane_select"] = transcript.mane_select or bool(
                resolved_transcript.mane_status
                and "mane" in resolved_transcript.mane_status.lower()
            )
        if transcript_update:
            transcript = transcript.model_copy(update=transcript_update)
            update["transcript"] = transcript
    elif resolved_transcript.transcript and not resolved_transcript.suggestion_only:
        update["transcript"] = _transcript_model(resolved_transcript, resolved_protein)
    if resolved_protein.hgvs_p and not variant.hgvs_p:
        update["hgvs_p"] = resolved_protein.hgvs_p
    if resolved_coordinate.hgvs_g and not variant.hgvs_g:
        update["hgvs_g"] = resolved_coordinate.hgvs_g
    if can_apply_coordinate_to_variant(variant, coordinate_flags) and all(
        (resolved_coordinate.genome_build, resolved_coordinate.chrom, resolved_coordinate.pos, resolved_coordinate.ref, resolved_coordinate.alt)
    ):
        update.update(
            {
                "genome_build": GenomeBuild(resolved_coordinate.genome_build),
                "chrom": str(resolved_coordinate.chrom),
                "pos": int(resolved_coordinate.pos),
                "ref": str(resolved_coordinate.ref),
                "alt": str(resolved_coordinate.alt),
                "variant_type": _variant_type(str(resolved_coordinate.ref), str(resolved_coordinate.alt)),
            }
        )
        update["variant_id"] = (
            f"{resolved_coordinate.genome_build}-{resolved_coordinate.chrom}-"
            f"{resolved_coordinate.pos}-{resolved_coordinate.ref}-{resolved_coordinate.alt}"
        )
    return variant.model_copy(update=update)


def _enriched_context(
    context: GeneDiseaseContext | None,
    variant: Variant,
    exon_context: Any,
    nmd_context: Any,
    *,
    preserve_manual_nmd_context: bool = False,
) -> GeneDiseaseContext | None:
    if context is None:
        return None
    update: dict[str, Any] = {}
    if not preserve_manual_nmd_context and exon_context.exon_number and exon_context.total_exons:
        update["last_exon_information"] = LastExonInformation(
            is_in_last_exon=exon_context.last_exon,
            is_in_penultimate_exon=exon_context.penultimate_exon,
            exon_number=exon_context.exon_number,
            total_exons=exon_context.total_exons,
            distance_to_last_exon_junction=exon_context.distance_to_last_exon_junction,
            within_terminal_region=bool(exon_context.last_exon),
            predicted_to_escape_nmd=nmd_context.nmd_unlikely,
        )
    if not preserve_manual_nmd_context and nmd_context.status != "unknown":
        update["nmd_prediction_available"] = True
        update["nmd_predicted"] = nmd_context.nmd_expected
    if variant.transcript and context.transcript is None:
        update["transcript"] = variant.transcript
    return context.model_copy(update=update)


def _transcript_model(resolved_transcript: Any, resolved_protein: Any) -> Transcript:
    return Transcript(
        accession=resolved_transcript.accession or resolved_transcript.transcript,
        version=resolved_transcript.version,
        gene_symbol=resolved_transcript.gene_symbol or "unknown",
        hgvs_p=resolved_protein.hgvs_p,
        consequence=resolved_protein.consequence,
        mane_select=bool(resolved_transcript.mane_status and "mane" in resolved_transcript.mane_status.lower()),
        canonical=resolved_transcript.transcript_source == "canonical_recommendation",
    )


def _step(name: str, confidence: float) -> ResolutionStep:
    status = "resolved" if confidence > 0 else "unresolved"
    return ResolutionStep(step_name=name, status=status, confidence=confidence)


def _variant_transcript(variant: Variant) -> str | None:
    if variant.transcript is None:
        return None
    if variant.transcript.version:
        return f"{variant.transcript.accession}.{variant.transcript.version}"
    return variant.transcript.accession


def _variant_type(ref: str, alt: str) -> VariantType:
    if len(ref) == 1 and len(alt) == 1:
        return VariantType.SNV
    if len(ref) > len(alt):
        return VariantType.SMALL_DELETION
    if len(ref) < len(alt):
        return VariantType.SMALL_INSERTION
    return VariantType.SMALL_DELINS


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
