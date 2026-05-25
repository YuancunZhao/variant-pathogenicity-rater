from __future__ import annotations

import re

from variant_pathogenicity_rater.pvs1.schema import NMDPrediction
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext


def evaluate_nmd_likelihood(
    context: GeneDiseaseContext,
    annotation: VariantAnnotation | None = None,
) -> NMDPrediction:
    last = context.last_exon_information
    if context.nmd_prediction_available and context.nmd_predicted is not None:
        return NMDPrediction(
            nmd_likely=context.nmd_predicted,
            terminal_region_risk=context.nmd_predicted is False,
            exon_position_known=last is not None,
            exon_number=last.exon_number if last else None,
            total_exons=last.total_exons if last else None,
            confidence=0.85,
            source="manual_context",
        )
    if last is not None:
        terminal = determine_terminal_exon_risk(context)
        if last.predicted_to_escape_nmd is True or terminal:
            return NMDPrediction(
                nmd_likely=False,
                terminal_region_risk=True,
                exon_position_known=True,
                exon_number=last.exon_number,
                total_exons=last.total_exons,
                confidence=0.75,
                source="last_exon_information",
                limitations=["Possible nonsense-mediated decay escape; PVS1 strength is downgraded."],
            )
        if last.is_in_last_exon is False and last.within_terminal_region is not True:
            return NMDPrediction(
                nmd_likely=True,
                terminal_region_risk=False,
                exon_position_known=True,
                exon_number=last.exon_number,
                total_exons=last.total_exons,
                confidence=0.72,
                source="last_exon_information",
            )
    exon_number, total_exons = estimate_exon_position_from_annotation(annotation)
    if exon_number and total_exons:
        terminal = exon_number >= total_exons
        penultimate_terminal = exon_number == total_exons - 1
        return NMDPrediction(
            nmd_likely=False if terminal else None,
            terminal_region_risk=terminal or penultimate_terminal,
            exon_position_known=True,
            exon_number=exon_number,
            total_exons=total_exons,
            confidence=0.45,
            source="annotation_exon",
            limitations=["Exon position was parsed from annotation only; terminal 50 nt could not be confirmed."],
        )
    return NMDPrediction(
        nmd_likely=None,
        exon_position_known=False,
        confidence=0.0,
        source="unknown",
        limitations=["NMD likelihood cannot be assumed without exon count, exon position, or explicit NMD context."],
    )


def determine_terminal_exon_risk(context: GeneDiseaseContext) -> bool:
    last = context.last_exon_information
    if last is None:
        return False
    return bool(
        last.is_in_last_exon
        or last.within_terminal_region
        or last.predicted_to_escape_nmd
        or (
            last.is_in_penultimate_exon
            and last.distance_to_last_exon_junction is not None
            and last.distance_to_last_exon_junction <= 50
        )
    )


def estimate_exon_position_from_annotation(annotation: VariantAnnotation | None) -> tuple[int | None, int | None]:
    if annotation is None or not annotation.exon:
        return None, None
    match = re.search(r"(\d+)\s*/\s*(\d+)", annotation.exon)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def use_hgvs_position_as_fallback() -> NMDPrediction:
    return NMDPrediction(
        nmd_likely=None,
        confidence=0.1,
        source="hgvs_position_fallback",
        limitations=["HGVS position alone is insufficient to infer NMD; candidate-only review is required."],
    )
