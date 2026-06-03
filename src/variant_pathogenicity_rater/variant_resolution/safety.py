from __future__ import annotations

from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.variant import Variant
from variant_pathogenicity_rater.transcript_support.validation import canonicalize_transcript
from variant_pathogenicity_rater.variant_resolution.schema import (
    ResolvedCoordinate,
    VariantResolutionRecord,
)


def coordinate_conflicts(variant: Variant, coordinate: ResolvedCoordinate | None) -> list[ReviewFlag]:
    if coordinate is None or not all((coordinate.chrom, coordinate.pos, coordinate.ref, coordinate.alt)):
        return []
    flags: list[ReviewFlag] = []
    supplied_coordinate = variant.chrom != "unresolved" and variant.pos > 1
    supplied_alleles = "N" not in {variant.ref.upper(), variant.alt.upper()}
    if supplied_coordinate and (
        str(coordinate.chrom) != str(variant.chrom) or int(coordinate.pos or 0) != variant.pos
    ):
        flags.append(
            ReviewFlag(
                code="RESOLUTION_COORDINATE_CONFLICT",
                message="Resolved coordinate conflicts with the user/local normalized coordinate; user coordinate was preserved.",
                severity="error",
                blocking=True,
            )
        )
    if supplied_alleles and (
        str(coordinate.ref or "").upper() != variant.ref.upper()
        or str(coordinate.alt or "").upper() != variant.alt.upper()
    ):
        flags.append(
            ReviewFlag(
                code="RESOLUTION_ALLELE_CONFLICT",
                message="Resolved ref/alt conflicts with the user/local normalized alleles; user alleles were preserved.",
                severity="error",
                blocking=True,
            )
        )
    return flags


def resolution_consistency_flags(
    variant: Variant,
    record: VariantResolutionRecord | None,
    coordinate: ResolvedCoordinate | None,
) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    if coordinate and coordinate.genome_build and str(coordinate.genome_build) != str(variant.genome_build):
        flags.append(
            ReviewFlag(
                code="RESOLUTION_BUILD_MISMATCH",
                message="Resolved genome build conflicts with the input genome build; input build and coordinates were preserved.",
                severity="error",
                blocking=True,
            )
        )

    input_transcript = _variant_transcript(variant)
    if not input_transcript or record is None or not record.transcript:
        return flags

    observed = canonicalize_transcript(input_transcript)
    expected = canonicalize_transcript(record.transcript)
    if observed.accession and expected.accession and observed.accession != expected.accession:
        flags.append(
            ReviewFlag(
                code="RESOLUTION_TRANSCRIPT_MISMATCH",
                message="Input transcript accession conflicts with the matched resolution record; input transcript was preserved.",
                severity="error",
                blocking=True,
            )
        )
    elif (
        observed.accession
        and expected.accession
        and observed.accession == expected.accession
        and observed.version
        and expected.version
        and observed.version != expected.version
    ):
        flags.append(
            ReviewFlag(
                code="RESOLUTION_TRANSCRIPT_VERSION_MISMATCH",
                message="Input transcript version differs from the matched resolution record; input transcript version was preserved.",
                severity="warning",
                blocking=True,
            )
        )
    return flags


def can_apply_coordinate_to_variant(variant: Variant, flags: list[ReviewFlag]) -> bool:
    if any(
        flag.code
        in {
            "RESOLUTION_BUILD_MISMATCH",
            "RESOLUTION_COORDINATE_CONFLICT",
            "RESOLUTION_ALLELE_CONFLICT",
        }
        for flag in flags
    ):
        return False
    unresolved_coordinate = variant.chrom == "unresolved" or variant.pos <= 1
    unresolved_alleles = "N" in {variant.ref.upper(), variant.alt.upper()}
    return unresolved_coordinate or unresolved_alleles


def unique_flags(flags: list[ReviewFlag]) -> list[ReviewFlag]:
    seen: set[str] = set()
    output: list[ReviewFlag] = []
    for flag in flags:
        if flag.code in seen:
            continue
        seen.add(flag.code)
        output.append(flag)
    return output


def _variant_transcript(variant: Variant) -> str | None:
    if variant.transcript is None:
        return None
    if variant.transcript.version:
        return f"{variant.transcript.accession}.{variant.transcript.version}"
    return variant.transcript.accession
