from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.pvs1.schema import ConsequenceAssessment, NMDPrediction, SplicePVS1Assessment
from variant_pathogenicity_rater.schemas.common import ReviewFlag


def evaluate_splice_pvs1_path(
    consequence: ConsequenceAssessment,
    nmd: NMDPrediction,
    provider_data: dict[str, Any] | None = None,
) -> SplicePVS1Assessment:
    provider_data = provider_data or {}
    if not consequence.is_splice:
        return SplicePVS1Assessment(applicable=False)

    path = ["Canonical or splice-region consequence detected."]
    limitations: list[str] = []
    flags: list[ReviewFlag] = []
    predicted_effect = provider_data.get("predicted_splice_effect")
    rna_evidence = bool(provider_data.get("rna_evidence"))
    frameshift_after_splice = provider_data.get("exon_skipping_frameshift")
    inframe_or_rescue = provider_data.get("inframe_exon_skipping") or provider_data.get("cryptic_rescue_possible")

    if rna_evidence:
        path.append("RNA evidence was supplied for splice consequence.")
        flags.append(ReviewFlag(code="PVS1_RNA_REVIEW", message="RNA-supported PVS1 must be manually reviewed and should not be double-counted with PP3.", severity="warning"))
        if nmd.nmd_likely is True:
            return SplicePVS1Assessment(
                applicable=True,
                predicted_effect=predicted_effect or "rna_supported_splice_lof",
                frameshift_after_splice=frameshift_after_splice,
                inframe_or_rescue_possible=bool(inframe_or_rescue),
                rna_evidence=True,
                suggested_strength="PVS1_Moderate",
                candidate_only=False,
                review_flags=flags,
                limitations=["RNA evidence is represented as suggested PVS1_RNA-style evidence and requires manual review."],
                path=path,
            )

    if inframe_or_rescue:
        limitations.append("Predicted in-frame exon skipping or cryptic rescue makes splice PVS1 candidate-only.")
        flags.append(ReviewFlag(code="SPLICE_INFRAME_RESCUE_POSSIBLE", message="In-frame splice rescue must be adjudicated before PVS1 is applied.", severity="error", blocking=True))
        return SplicePVS1Assessment(
            applicable=True,
            predicted_effect=predicted_effect or "inframe_or_rescue_possible",
            frameshift_after_splice=False,
            inframe_or_rescue_possible=True,
            suggested_strength="PVS1_candidate",
            candidate_only=True,
            review_flags=flags,
            limitations=limitations,
            path=path,
        )

    if frameshift_after_splice is True and nmd.nmd_likely is True:
        path.append("Predicted exon skipping creates a frameshift and NMD is likely.")
        limitations.append("Splice effect is predicted, not validated by RNA.")
        return SplicePVS1Assessment(
            applicable=True,
            predicted_effect=predicted_effect or "predicted_exon_skipping_frameshift",
            frameshift_after_splice=True,
            inframe_or_rescue_possible=False,
            suggested_strength="PVS1_Moderate",
            candidate_only=False,
            limitations=limitations,
            path=path,
        )

    limitations.append("Canonical splice consequence lacks validated RNA consequence; conservative candidate/supporting review only.")
    flags.append(ReviewFlag(code="SPLICE_CONSEQUENCE_UNCERTAIN", message="Canonical splice does not automatically equal PVS1 Very Strong.", severity="warning"))
    return SplicePVS1Assessment(
        applicable=True,
        predicted_effect=predicted_effect or "splice_effect_uncertain",
        frameshift_after_splice=frameshift_after_splice,
        inframe_or_rescue_possible=None,
        suggested_strength="PVS1_Supporting",
        candidate_only=True,
        review_flags=flags,
        limitations=limitations,
        path=path,
    )
