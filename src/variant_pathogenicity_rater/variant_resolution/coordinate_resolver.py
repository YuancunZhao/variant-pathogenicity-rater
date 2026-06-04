from __future__ import annotations

from variant_pathogenicity_rater.schemas.variant import Variant
from variant_pathogenicity_rater.variant_resolution.schema import ResolvedCoordinate, VariantResolutionRecord


def resolve_coordinate(
    record: VariantResolutionRecord | None,
    *,
    fallback_variant: Variant | None = None,
) -> ResolvedCoordinate:
    if record and all((record.genome_build, record.chrom, record.pos, record.ref, record.alt)):
        return ResolvedCoordinate(
            genome_build=record.genome_build,
            chrom=record.chrom,
            pos=record.pos,
            ref=record.ref,
            alt=record.alt,
            hgvs_g=record.hgvs_g,
            confidence=record.confidence,
            limitations=[],
            provenance=[_record_provenance(record)],
        )
    if fallback_variant is not None and _has_structured_coordinate(fallback_variant):
        return ResolvedCoordinate(
            genome_build=str(fallback_variant.genome_build),
            chrom=fallback_variant.chrom,
            pos=fallback_variant.pos,
            ref=fallback_variant.ref,
            alt=fallback_variant.alt,
            hgvs_g=fallback_variant.hgvs_g,
            confidence=0.75,
            limitations=[
                "Genomic coordinate was inherited from the normalized structured input; no local resolution fixture coordinate was available."
            ],
            provenance=[
                {
                    "source": "normalized_variant",
                    "scope": "variant resolution only; not ACMG evidence",
                    "variant_id": fallback_variant.variant_id,
                }
            ],
        )
    return ResolvedCoordinate(
        confidence=0.0,
        limitations=["Genomic coordinate could not be resolved from local fixtures."],
    )


def _has_structured_coordinate(variant: Variant) -> bool:
    return (
        bool(variant.chrom)
        and variant.chrom != "unresolved"
        and variant.pos > 1
        and "N" not in {variant.ref.upper(), variant.alt.upper()}
    )


def _record_provenance(record: VariantResolutionRecord | None) -> dict:
    if record is None:
        return {}
    return {
        "source": record.source,
        "source_version": record.source_version,
        "raw_snapshot_ref": record.raw_snapshot_ref,
        **record.provenance,
    }
