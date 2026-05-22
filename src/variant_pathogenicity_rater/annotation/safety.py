from __future__ import annotations

from variant_pathogenicity_rater.schemas.annotation import AnnotationParseResult, VariantAnnotation
from variant_pathogenicity_rater.schemas.common import ReviewFlag


def evaluate_annotation_safety(
    annotations: list[VariantAnnotation],
    *,
    expected_transcript: str | None = None,
) -> AnnotationParseResult:
    review_flags: list[ReviewFlag] = []
    limitations: list[str] = [
        "Annotation and normalization are descriptive only; they do not directly generate ACMG evidence."
    ]

    transcripts = {annotation.transcript for annotation in annotations if annotation.transcript}
    if len(transcripts) > 1:
        review_flags.append(
            ReviewFlag(
                code="MULTIPLE_TRANSCRIPT_AMBIGUITY",
                message="Multiple annotated transcripts are present; transcript selection requires review.",
                severity="warning",
            )
        )
    if expected_transcript and transcripts and expected_transcript not in transcripts:
        review_flags.append(
            ReviewFlag(
                code="TRANSCRIPT_MISMATCH",
                message=(
                    f"Expected transcript {expected_transcript} was not found in annotation transcripts: "
                    f"{', '.join(sorted(transcripts))}."
                ),
                severity="warning",
            )
        )

    for annotation in annotations:
        if not annotation.hgvs_c and not annotation.hgvs_p:
            limitations.append(
                f"Missing HGVS for {annotation.annotation_source} annotation"
                f"{_transcript_suffix(annotation)}."
            )
        if annotation.mane_select or annotation.canonical:
            limitations.append(
                "MANE Select and canonical tags may assist transcript selection but are not ACMG evidence."
            )

    return AnnotationParseResult(
        annotations=annotations,
        review_flags=_unique_flags(review_flags),
        limitations=_unique(limitations),
    )


def _transcript_suffix(annotation: VariantAnnotation) -> str:
    return f" on {annotation.transcript}" if annotation.transcript else ""


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _unique_flags(flags: list[ReviewFlag]) -> list[ReviewFlag]:
    seen: set[str] = set()
    unique: list[ReviewFlag] = []
    for flag in flags:
        if flag.code in seen:
            continue
        seen.add(flag.code)
        unique.append(flag)
    return unique
