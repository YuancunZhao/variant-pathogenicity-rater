from __future__ import annotations

from variant_pathogenicity_rater.ps1_pm5.schema import ClinVarComparison
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord
from variant_pathogenicity_rater.schemas.variant import Variant


def compare_clinvar_record(variant: Variant, record: ClinVarRecord) -> ClinVarComparison:
    significance = (record.clinical_significance or "").lower()
    conflict_status = (record.conflict_status or "").lower()
    has_conflict = (
        record.conflicting_interpretations
        or "conflicting" in significance
        or "conflict" in conflict_status
    )
    is_plp = _is_pathogenic_or_likely_pathogenic(significance)
    is_germline = _is_germline_applicable(record)
    low_quality = _low_quality(record)
    high_quality = is_plp and not has_conflict and is_germline and not low_quality
    query_genomic = _genomic_key(
        str(variant.genome_build),
        variant.chrom,
        variant.pos,
        variant.ref,
        variant.alt,
    )
    comparator_genomic = _genomic_key(
        record.genome_build,
        record.chromosome,
        record.position,
        record.ref,
        record.alt,
    )
    same_hgvs_c = bool(
        variant.hgvs_c and record.hgvs_c and variant.hgvs_c == record.hgvs_c
    )
    same_genomic = bool(
        query_genomic and comparator_genomic and query_genomic == comparator_genomic
    )
    different_hgvs_c = bool(
        variant.hgvs_c and record.hgvs_c and variant.hgvs_c != record.hgvs_c
    )
    different_genomic = bool(
        query_genomic and comparator_genomic and query_genomic != comparator_genomic
    )

    return ClinVarComparison(
        variation_id=record.variation_id,
        clinical_significance=record.clinical_significance,
        review_status=record.review_status,
        review_stars=record.review_stars,
        submitter_count=record.submitter_count,
        conflict_status=record.conflict_status,
        germline_or_somatic=record.germline_or_somatic,
        citations=record.citations,
        is_pathogenic_or_likely_pathogenic=is_plp,
        has_conflict=has_conflict,
        is_germline_applicable=is_germline,
        high_quality_for_applied=high_quality,
        low_quality_candidate_only=low_quality,
        same_nucleotide_change=same_hgvs_c or same_genomic,
        different_nucleotide_change=different_hgvs_c or different_genomic,
        query_hgvs_c=variant.hgvs_c,
        comparator_hgvs_c=record.hgvs_c,
        query_genomic_key=query_genomic,
        comparator_genomic_key=comparator_genomic,
        source_snapshot=record.source.database_id,
        source_version=record.source.version,
        raw_snapshot_ref=record.source.raw_snapshot_ref,
    )


def _is_pathogenic_or_likely_pathogenic(significance: str) -> bool:
    if "benign" in significance:
        return False
    return "pathogenic" in significance or "likely pathogenic" in significance


def _is_germline_applicable(record: ClinVarRecord) -> bool:
    value = (record.germline_or_somatic or "").lower()
    return not ("somatic" in value and "germline" not in value)


def _low_quality(record: ClinVarRecord) -> bool:
    status = (record.review_status or "").lower()
    return (
        not status
        or "single submitter" in status
        or "no assertion criteria" in status
        or "no assertion provided" in status
        or (record.review_stars is not None and record.review_stars <= 1)
        or record.submitter_count == 1
    )


def _genomic_key(
    genome_build: str | None,
    chrom: str | None,
    pos: int | None,
    ref: str | None,
    alt: str | None,
) -> str | None:
    if not all([genome_build, chrom, pos, ref, alt]):
        return None
    return f"{genome_build}:{str(chrom).removeprefix('chr')}:{pos}:{ref}>{alt}".upper()
