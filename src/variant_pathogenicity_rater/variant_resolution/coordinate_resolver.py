from __future__ import annotations

from variant_pathogenicity_rater.variant_resolution.schema import ResolvedCoordinate, VariantResolutionRecord


def resolve_coordinate(record: VariantResolutionRecord | None) -> ResolvedCoordinate:
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
    return ResolvedCoordinate(
        confidence=0.0,
        limitations=["Genomic coordinate could not be resolved from local fixtures."],
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
