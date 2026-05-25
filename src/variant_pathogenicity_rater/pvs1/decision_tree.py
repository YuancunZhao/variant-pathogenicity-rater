from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.pvs1.consequence import parse_variant_consequence
from variant_pathogenicity_rater.pvs1.lof_mechanism import resolve_lof_mechanism
from variant_pathogenicity_rater.pvs1.nmd import evaluate_nmd_likelihood
from variant_pathogenicity_rater.pvs1.safety import enforce_pvs1_safety
from variant_pathogenicity_rater.pvs1.schema import PVS1Config, PVS1Decision
from variant_pathogenicity_rater.pvs1.splice import evaluate_splice_pvs1_path
from variant_pathogenicity_rater.pvs1.transcript import evaluate_transcript_relevance
from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


def run_pvs1_decision_tree(
    variant: Variant,
    *,
    annotation: VariantAnnotation | None = None,
    transcript_selection: TranscriptSelection | None = None,
    gene_disease_context: GeneDiseaseContext | None = None,
    context_consistency: ContextConsistency | None = None,
    provider_data: dict[str, Any] | None = None,
    manual_overrides: dict[str, Any] | None = None,
    config: PVS1Config | None = None,
) -> PVS1Decision:
    config = config or PVS1Config()
    context = gene_disease_context or GeneDiseaseContext(
        gene=variant.gene_symbol or "unknown",
        disease="not provided",
    )
    path: list[str] = []
    blocking: list[str] = []
    downgrades: list[str] = []
    limitations: list[str] = []
    review_flags: list[ReviewFlag] = []

    consequence = parse_variant_consequence(variant, annotation, variant.transcript or context.transcript, provider_data)
    path.append(f"1. consequence: {consequence.primary_consequence or 'none'}; lof={consequence.is_lof}.")
    limitations.extend(consequence.limitations)
    if not consequence.is_lof:
        blocking.append("No supported LoF consequence was detected.")

    if _missing_context(context):
        blocking.append("Disease/inheritance context is missing or incomplete.")
        review_flags.append(_flag("MISSING_DISEASE_CONTEXT", "Applied PVS1 requires gene, disease, and inheritance context.", True))

    lof = resolve_lof_mechanism(variant, context, config=config, manual_overrides=manual_overrides)
    path.append(f"2. LoF mechanism: {lof.status} via {lof.source}.")
    limitations.extend(lof.limitations)
    if lof.lof_is_known is not True:
        blocking.append("LoF is not confirmed as a disease mechanism for this gene-disease context.")
        review_flags.append(_flag("LOF_MECHANISM_NOT_CONFIRMED", "PVS1 is not applied unless LoF is a known disease mechanism.", True))

    transcript = evaluate_transcript_relevance(variant, annotation, transcript_selection, context)
    path.append(f"3. transcript relevance: {transcript.relevant}; transcript={transcript.transcript or 'unknown'}.")
    limitations.extend(transcript.limitations)
    review_flags.extend(transcript.review_flags)
    if transcript.relevant is not True:
        blocking.append("Transcript relevance is missing, mismatched, non-coding, or ambiguous.")

    nmd = evaluate_nmd_likelihood(context, annotation)
    path.append(f"4. NMD/exon: nmd_likely={nmd.nmd_likely}; terminal_risk={nmd.terminal_region_risk}.")
    limitations.extend(nmd.limitations)
    if nmd.nmd_likely is None:
        downgrades.append("NMD likelihood is unknown; PVS1 strength is capped below Strong.")
        review_flags.append(_flag("NMD_UNKNOWN", "NMD likelihood cannot be assumed from incomplete exon data.", False))
    if nmd.terminal_region_risk:
        downgrades.append("Last exon or terminal-region NMD escape risk.")

    splice = evaluate_splice_pvs1_path(consequence, nmd, provider_data)
    if splice.applicable:
        path.extend(f"5. splice: {item}" for item in splice.path)
        limitations.extend(splice.limitations)
        review_flags.extend(splice.review_flags)
        if splice.candidate_only:
            downgrades.append("Splice consequence is insufficiently certain for applied PVS1.")

    if consequence.rescue_risk:
        blocking.append("Possible in-frame rescue or preserved reading frame.")
        review_flags.append(_flag("POSSIBLE_IN_FRAME_RESCUE", "Possible in-frame rescue blocks applied PVS1 pending review.", True))
    if consequence.primary_consequence in {"start_lost", "stop_lost", "splice_region_variant"}:
        blocking.append(f"{consequence.primary_consequence} is candidate-only by default.")
    if consequence.splice_uncertainty and not (splice.applicable and splice.candidate_only is False):
        blocking.append("Splice consequence is uncertain without RNA or a predicted frameshift exon-skipping path.")

    if context_consistency is not None:
        path.append(f"7. context consistency: {context_consistency.status}.")
        limitations.extend(context_consistency.limitations)
        if context_consistency.conflicts:
            blocking.append("Major context consistency conflict is present.")
            review_flags.append(_flag("CONTEXT_CONFLICT", "Context consistency conflict blocks applied PVS1.", True))
    else:
        path.append("7. context consistency: not supplied.")

    strength = _strength(consequence.primary_consequence, nmd.nmd_likely, nmd.terminal_region_risk, splice.suggested_strength if splice.applicable else None)
    path.append(f"8. final strength before safety: {strength}.")
    applied = not blocking and strength not in {"PVS1_candidate", "not_applicable"}
    candidate_only = not applied
    recommended = strength if strength != "not_applicable" else "not_applicable"
    if candidate_only and consequence.is_lof:
        recommended = "PVS1_candidate"
        strength = "PVS1_candidate"

    decision = PVS1Decision(
        recommended_code=recommended,
        strength=strength,
        applied=applied,
        candidate_only=candidate_only,
        decision_path=path,
        downgrade_reasons=_unique(downgrades),
        blocking_reasons=_unique(blocking),
        review_flags=_unique_flags(review_flags),
        limitations=_unique(limitations),
        provenance=[*lof.provenance],
        consequence=consequence,
        lof_mechanism=lof,
        transcript_relevance=transcript,
        nmd=nmd,
        splice=splice,
    )
    return enforce_pvs1_safety(decision)


def _strength(
    consequence: str | None,
    nmd_likely: bool | None,
    terminal_region_risk: bool,
    splice_strength: str | None,
) -> str:
    if consequence is None:
        return "not_applicable"
    if splice_strength:
        return splice_strength
    if consequence in {"start_lost", "stop_lost", "splice_region_variant"}:
        return "PVS1_candidate"
    if nmd_likely is True and not terminal_region_risk:
        return "PVS1"
    if nmd_likely is False or terminal_region_risk:
        return "PVS1_Supporting"
    return "PVS1_Supporting"


def _missing_context(context: GeneDiseaseContext) -> bool:
    missing_disease = context.disease_name.strip().lower() in {"", "unknown", "not provided", "unspecified", "not specified"}
    missing_gene = context.gene_symbol.strip().lower() in {"", "unknown"}
    return missing_gene or missing_disease or not context.inheritance_mode


def _flag(code: str, message: str, blocking: bool) -> ReviewFlag:
    return ReviewFlag(code=code, message=message, severity="error" if blocking else "warning", blocking=blocking)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _unique_flags(flags: list[ReviewFlag]) -> list[ReviewFlag]:
    seen: set[str] = set()
    output: list[ReviewFlag] = []
    for flag in flags:
        if flag.code in seen:
            continue
        seen.add(flag.code)
        output.append(flag)
    return output
