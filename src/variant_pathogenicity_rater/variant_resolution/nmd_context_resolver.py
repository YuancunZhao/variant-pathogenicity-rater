from __future__ import annotations

from variant_pathogenicity_rater.variant_resolution.schema import ExonContext, NMDContext, VariantResolutionRecord


def resolve_nmd_context(record: VariantResolutionRecord | None, exon_context: ExonContext | None) -> NMDContext:
    if record and record.nmd_status:
        return _context(record.nmd_status, record.confidence, [_record_provenance(record)])
    if exon_context and exon_context.exon_number and exon_context.total_exons:
        if exon_context.last_exon:
            return _context("NMD_unlikely", min(exon_context.confidence, 0.75), exon_context.provenance)
        if exon_context.penultimate_exon and (
            exon_context.distance_to_last_exon_junction is None
            or exon_context.distance_to_last_exon_junction <= 50
        ):
            return _context("NMD_unlikely", min(exon_context.confidence, 0.65), exon_context.provenance)
        return _context("NMD_expected", min(exon_context.confidence, 0.75), exon_context.provenance)
    return NMDContext(
        status="unknown",
        nmd_expected=None,
        nmd_unlikely=None,
        nmd_confidence=0.0,
        limitations=["NMD context could not be resolved from local exon/CDS fixtures."],
    )


def _context(status: str, confidence: float, provenance: list[dict]) -> NMDContext:
    return NMDContext(
        status=status,
        nmd_expected=status == "NMD_expected",
        nmd_unlikely=status == "NMD_unlikely",
        nmd_confidence=confidence,
        limitations=[],
        provenance=provenance,
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
