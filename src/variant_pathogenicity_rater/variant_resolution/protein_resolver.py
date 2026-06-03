from __future__ import annotations

from variant_pathogenicity_rater.schemas.variant import Variant
from variant_pathogenicity_rater.variant_resolution.schema import ResolvedProtein, VariantResolutionRecord


def resolve_protein(variant: Variant, record: VariantResolutionRecord | None) -> ResolvedProtein:
    if variant.hgvs_p:
        accession = variant.hgvs_p.split(":", 1)[0] if ":" in variant.hgvs_p else None
        return ResolvedProtein(
            hgvs_p=variant.hgvs_p,
            protein_accession=accession or (record.protein_accession if record else None),
            consequence=record.consequence if record else None,
            confidence=0.9 if record else 0.75,
            limitations=[],
            provenance=[_record_provenance(record)] if record else [],
        )
    if record and record.hgvs_p:
        return ResolvedProtein(
            hgvs_p=record.hgvs_p,
            protein_accession=record.protein_accession,
            consequence=record.consequence,
            confidence=record.confidence,
            limitations=[],
            provenance=[_record_provenance(record)],
        )
    return ResolvedProtein(
        confidence=0.0,
        limitations=["Protein consequence could not be resolved from local fixtures."],
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
