from __future__ import annotations

from variant_pathogenicity_rater.pvs1.schema import TranscriptRelevanceAssessment
from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Transcript, Variant
from variant_pathogenicity_rater.transcript_support.schema import TranscriptValidationResult


def evaluate_transcript_relevance(
    variant: Variant,
    annotation: VariantAnnotation | None = None,
    transcript_selection: TranscriptSelection | None = None,
    transcript_validation: TranscriptValidationResult | None = None,
    context: GeneDiseaseContext | None = None,
) -> TranscriptRelevanceAssessment:
    transcript = variant.transcript or (context.transcript if context else None)
    label = _label(transcript) or (annotation.transcript if annotation else None)
    limitations: list[str] = []
    flags: list[ReviewFlag] = []
    confidence = 0.0
    relevant: bool | None = None
    source = "unknown"

    if transcript_selection is not None:
        if transcript_selection.limitations:
            limitations.extend(transcript_selection.limitations)
        if transcript_selection.review_flags:
            flags.extend(transcript_selection.review_flags)
        if transcript_selection.user_transcript_provided and not transcript_selection.user_transcript_matched:
            limitations.append("User transcript did not match annotation transcript selection.")
            flags.append(_flag("TRANSCRIPT_MISMATCH", "User transcript and annotation-selected transcript do not match.", True))
            return _assessment(False, 0.1, label, "transcript_selection", flags, limitations, transcript_selection)
        if len(transcript_selection.candidate_transcripts) > 1 and transcript_selection.selection_confidence < 0.8:
            limitations.append("Multiple similarly plausible transcripts are present.")
            flags.append(_flag("MULTIPLE_TRANSCRIPT_AMBIGUITY", "Multiple transcript candidates require manual review.", True))
            return _assessment(None, 0.3, transcript_selection.selected_transcript, "transcript_selection", flags, limitations, transcript_selection)
        if transcript_selection.selected_transcript:
            label = transcript_selection.selected_transcript
            relevant = True
            confidence = max(confidence, transcript_selection.selection_confidence)
            source = "transcript_selection"

    if transcript_validation is not None:
        limitations.extend(transcript_validation.limitations)
        flags.extend(transcript_validation.review_flags)
        summary = transcript_validation.model_dump(mode="json")
        if transcript_validation.matched_record:
            matched = transcript_validation.matched_record
            label = matched.get("transcript") or label
            if matched.get("mane_status"):
                source = "transcript_metadata"
            if matched.get("mane_status") or matched.get("canonical"):
                confidence = max(confidence, 0.82 if matched.get("mane_status") else 0.72)
            if matched.get("protein_coding") is False:
                return _assessment(False, 0.1, label, "transcript_metadata", flags, limitations, transcript_selection, summary)
            if str(matched.get("transcript_status") or "").strip().lower() in {"deprecated", "retired", "withdrawn", "obsolete", "replaced"}:
                return _assessment(False, 0.1, label, "transcript_metadata", flags, limitations, transcript_selection, summary)
        if transcript_validation.status == "conflict":
            return _assessment(False, 0.1, label, "transcript_metadata", flags, limitations, transcript_selection, summary)
        if transcript_validation.status in {"warning", "insufficient"} and relevant is not True:
            return _assessment(None, max(confidence, 0.35), label, "transcript_metadata", flags, limitations, transcript_selection, summary)

    if annotation is not None:
        if annotation.transcript_biotype and annotation.transcript_biotype != "protein_coding":
            limitations.append("Selected annotation transcript is not protein_coding.")
            flags.append(_flag("NON_CODING_TRANSCRIPT", "PVS1 requires a protein-coding biologically relevant transcript.", True))
            return _assessment(False, 0.1, label, "annotation", flags, limitations, transcript_selection)
        if annotation.mane_select:
            relevant = True
            confidence = max(confidence, 0.82)
            source = "MANE_Select"
        elif annotation.canonical:
            relevant = True
            confidence = max(confidence, 0.72)
            source = "canonical_annotation"

    if context and context.transcript_is_biologically_relevant is True:
        relevant = True
        confidence = max(confidence, 0.85)
        source = "manual_context"
    elif context and context.transcript_is_biologically_relevant is False:
        flags.append(_flag("TRANSCRIPT_RELEVANCE_NOT_CONFIRMED", "Context says transcript is not biologically relevant.", True))
        return _assessment(False, 0.1, label, "manual_context", flags, limitations, transcript_selection)

    if transcript is not None and annotation is not None and annotation.transcript:
        if not _same_transcript(_label(transcript), annotation.transcript):
            limitations.append("Variant transcript does not match annotation transcript.")
            flags.append(_flag("TRANSCRIPT_MISMATCH", "Variant transcript and annotation transcript differ.", True))
            return _assessment(False, 0.1, label, "annotation", flags, limitations, transcript_selection)

    if label is None:
        limitations.append("Transcript is missing.")
        flags.append(_flag("TRANSCRIPT_MISSING", "Transcript is required for applied PVS1.", True))
        return _assessment(None, 0.0, None, source, flags, limitations, transcript_selection)

    if relevant is not True:
        limitations.append("Transcript biological relevance is not confirmed.")
        flags.append(_flag("TRANSCRIPT_RELEVANCE_NOT_CONFIRMED", "Transcript relevance is insufficient for applied PVS1.", True))
        return _assessment(None, max(confidence, 0.35), label, source, flags, limitations, transcript_selection)

    return _assessment(True, confidence or 0.7, label, source, flags, limitations, transcript_selection)


def _assessment(
    relevant: bool | None,
    confidence: float,
    transcript: str | None,
    source: str,
    flags: list[ReviewFlag],
    limitations: list[str],
    selection: TranscriptSelection | None,
    extra_summary: dict | None = None,
) -> TranscriptRelevanceAssessment:
    summary = selection.model_dump(mode="json") if selection else {}
    if extra_summary:
        summary["transcript_validation"] = extra_summary
    return TranscriptRelevanceAssessment(
        relevant=relevant,
        confidence=confidence,
        transcript=transcript,
        source=source,
        review_flags=flags,
        limitations=limitations,
        summary=summary,
    )


def _label(transcript: Transcript | None) -> str | None:
    if transcript is None:
        return None
    return f"{transcript.accession}.{transcript.version}" if transcript.version else transcript.accession


def _same_transcript(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return True
    return left == right or left.split(".")[0] == right.split(".")[0]


def _flag(code: str, message: str, blocking: bool) -> ReviewFlag:
    return ReviewFlag(code=code, message=message, severity="warning" if not blocking else "error", blocking=blocking)
