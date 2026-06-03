from __future__ import annotations

from variant_pathogenicity_rater.variant_resolution.schema import ExonContext, VariantResolutionRecord


def resolve_exon_context(record: VariantResolutionRecord | None) -> ExonContext:
    if record and record.exon_number and record.total_exons:
        return ExonContext(
            exon_number=record.exon_number,
            total_exons=record.total_exons,
            cds_position=record.cds_position,
            last_exon=record.exon_number == record.total_exons,
            penultimate_exon=record.exon_number == record.total_exons - 1,
            distance_to_last_exon_junction=record.distance_to_last_exon_junction,
            confidence=record.confidence,
            limitations=[],
            provenance=[_record_provenance(record)],
        )
    return ExonContext(
        confidence=0.0,
        limitations=["Exon context could not be resolved from local fixtures."],
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
