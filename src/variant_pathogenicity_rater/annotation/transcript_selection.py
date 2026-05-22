from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.schemas.annotation import (
    TranscriptSelection,
    VariantAnnotation,
)
from variant_pathogenicity_rater.schemas.common import ReviewFlag


SEVERE_CONSEQUENCE_RANK = {
    "transcript_ablation": 100,
    "splice_acceptor_variant": 95,
    "splice_donor_variant": 95,
    "stop_gained": 90,
    "frameshift_variant": 90,
    "stop_lost": 85,
    "start_lost": 80,
    "inframe_insertion": 70,
    "inframe_deletion": 70,
    "missense_variant": 60,
    "protein_altering_variant": 60,
    "splice_region_variant": 50,
    "synonymous_variant": 20,
    "intron_variant": 10,
    "upstream_gene_variant": 5,
    "downstream_gene_variant": 5,
}


def select_transcript(
    annotations: list[VariantAnnotation],
    *,
    user_transcript: str | None = None,
) -> TranscriptSelection:
    """Recommend a transcript for review without generating ACMG evidence."""

    review_flags: list[ReviewFlag] = []
    limitations = [
        "Transcript selection is descriptive only and does not trigger ACMG evidence."
    ]
    provenance: dict[str, Any] = {
        "selector": "offline_transcript_selection_v1",
        "input_annotation_count": len(annotations),
        "priority_order": [
            "user_transcript_if_matched",
            "mane_select",
            "biologically_relevant",
            "canonical",
            "protein_coding",
            "severe_consequence_tiebreaker",
        ],
    }

    if not annotations:
        limitations.append("No annotation records were available for transcript selection.")
        review_flags.append(
            ReviewFlag(
                code="MISSING_TRANSCRIPT_ANNOTATION",
                message="No annotation records were available; transcript choice requires review.",
                severity="warning",
                blocking=False,
            )
        )
        return TranscriptSelection(
            selection_reason="No annotation records were supplied.",
            selection_confidence=0.0,
            user_transcript_provided=bool(user_transcript),
            review_flags=review_flags,
            limitations=_unique(limitations),
            provenance=provenance,
        )

    candidates = [_candidate(annotation) for annotation in annotations]
    mane_available = any(candidate["mane_select"] for candidate in candidates)
    canonical_available = any(candidate["canonical"] for candidate in candidates)
    relevant_available = any(candidate["biologically_relevant"] for candidate in candidates)

    if user_transcript:
        match = _match_user_transcript(candidates, user_transcript)
        if match:
            selected = match
            reason = "User-provided transcript matched annotation and was preserved."
            confidence = 0.95
            rejected = [candidate for candidate in candidates if candidate is not selected]
            review_flags.extend(_global_conflict_flags(candidates))
            review_flags.extend(_selected_safety_flags(selected))
            return _selection(
                selected,
                candidates,
                rejected,
                reason,
                confidence,
                mane_available,
                canonical_available,
                relevant_available,
                user_transcript_provided=True,
                user_transcript_matched=True,
                review_flags=review_flags,
                limitations=limitations,
                provenance=provenance,
            )

        review_flags.append(
            ReviewFlag(
                code="USER_TRANSCRIPT_MISMATCH",
                message=(
                    f"User-provided transcript {user_transcript} was not found in annotation "
                    "records; no transcript was automatically substituted."
                ),
                severity="warning",
                blocking=True,
            )
        )
        limitations.append(
            "User-provided transcript was not present in annotation records; selected_transcript "
            "is intentionally left empty."
        )
        review_flags.extend(_global_conflict_flags(candidates))
        return TranscriptSelection(
            selected_transcript=None,
            selected_gene=None,
            selection_reason="User-provided transcript did not match annotation records.",
            selection_confidence=0.0,
            candidate_transcripts=candidates,
            rejected_transcripts=[],
            mane_select_available=mane_available,
            canonical_available=canonical_available,
            biologically_relevant_available=relevant_available,
            user_transcript_provided=True,
            user_transcript_matched=False,
            review_flags=_unique_flags(review_flags),
            limitations=_unique(limitations),
            provenance=provenance,
        )

    selected, reason, confidence, used_severity_tiebreaker = _select_without_user(candidates)
    rejected = [candidate for candidate in candidates if candidate is not selected]
    review_flags.extend(_global_conflict_flags(candidates))

    equal_candidates = _equal_priority_candidates(candidates, selected)
    if len(equal_candidates) > 1:
        review_flags.append(
            ReviewFlag(
                code="TRANSCRIPT_SELECTION_AMBIGUITY",
                message=(
                    "Multiple transcripts have equal selection priority; "
                    "human review is required."
                ),
                severity="warning",
                blocking=True,
            )
        )
        confidence = min(confidence, 0.5)

    if used_severity_tiebreaker:
        review_flags.append(
            ReviewFlag(
                code="SEVERE_CONSEQUENCE_TIEBREAKER_USED",
                message=(
                    "More severe consequence was used only as a tie-breaker; this must be "
                    "reviewed and is not ACMG evidence."
                ),
                severity="warning",
                blocking=True,
            )
        )
        confidence = min(confidence, 0.65)

    review_flags.extend(_selected_safety_flags(selected))
    return _selection(
        selected,
        candidates,
        rejected,
        reason,
        confidence,
        mane_available,
        canonical_available,
        relevant_available,
        user_transcript_provided=False,
        user_transcript_matched=False,
        review_flags=review_flags,
        limitations=limitations,
        provenance=provenance,
    )


def _candidate(annotation: VariantAnnotation) -> dict[str, Any]:
    terms = list(annotation.consequence_terms)
    if not terms and annotation.consequence:
        terms = [
            term.strip()
            for term in annotation.consequence.replace("&", ",").split(",")
            if term.strip()
        ]
    biologically_relevant = _as_bool(
        annotation.raw_fields.get("transcript_is_biologically_relevant")
        or annotation.raw_fields.get("biologically_relevant")
        or annotation.raw_fields.get("clinically_relevant")
    )
    severity = max((SEVERE_CONSEQUENCE_RANK.get(term, 0) for term in terms), default=0)
    return {
        "transcript": annotation.transcript,
        "gene": annotation.gene,
        "mane_select": bool(annotation.mane_select),
        "canonical": bool(annotation.canonical),
        "biologically_relevant": biologically_relevant,
        "protein_coding": annotation.transcript_biotype == "protein_coding",
        "transcript_biotype": annotation.transcript_biotype,
        "consequence": annotation.consequence,
        "consequence_terms": terms,
        "severity_rank": severity,
        "annotation_source": annotation.annotation_source,
    }


def _select_without_user(
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, float, bool]:
    tiers = [
        ("mane_select", "MANE Select transcript was preferred.", 0.9),
        (
            "biologically_relevant",
            "Biologically or clinically relevant transcript was preferred.",
            0.82,
        ),
        ("canonical", "Canonical transcript was used as fallback.", 0.74),
        ("protein_coding", "Protein-coding transcript was preferred.", 0.66),
    ]
    pool = candidates
    for key, reason, confidence in tiers:
        filtered = [candidate for candidate in pool if candidate[key]]
        if filtered:
            return _severity_tiebreak(filtered, reason, confidence)
    return _severity_tiebreak(candidates, "First available annotated transcript was used.", 0.45)


def _severity_tiebreak(
    candidates: list[dict[str, Any]],
    reason: str,
    confidence: float,
) -> tuple[dict[str, Any], str, float, bool]:
    if len(candidates) <= 1:
        return candidates[0], reason, confidence, False
    max_rank = max(candidate["severity_rank"] for candidate in candidates)
    severe = [candidate for candidate in candidates if candidate["severity_rank"] == max_rank]
    if len(severe) < len(candidates) and max_rank > 0:
        return (
            severe[0],
            f"{reason} More severe consequence was used as a tie-breaker.",
            confidence,
            True,
        )
    return candidates[0], reason, confidence, False


def _equal_priority_candidates(
    candidates: list[dict[str, Any]],
    selected: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_priority = _priority_tuple(selected, include_severity=False)
    return [
        candidate
        for candidate in candidates
        if _priority_tuple(candidate, include_severity=False) == selected_priority
    ]


def _priority_tuple(candidate: dict[str, Any], *, include_severity: bool) -> tuple[Any, ...]:
    values: tuple[Any, ...] = (
        candidate["mane_select"],
        candidate["biologically_relevant"],
        candidate["canonical"],
        candidate["protein_coding"],
    )
    if include_severity:
        return (*values, candidate["severity_rank"])
    return values


def _match_user_transcript(
    candidates: list[dict[str, Any]],
    user_transcript: str,
) -> dict[str, Any] | None:
    normalized_user = _normalize_transcript(user_transcript)
    for candidate in candidates:
        transcript = candidate.get("transcript")
        if transcript and (
            transcript == user_transcript or _normalize_transcript(transcript) == normalized_user
        ):
            return candidate
    return None


def _global_conflict_flags(candidates: list[dict[str, Any]]) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    mane = [candidate for candidate in candidates if candidate["mane_select"]]
    canonical = [candidate for candidate in candidates if candidate["canonical"]]
    if len(mane) > 1:
        flags.append(
            ReviewFlag(
                code="MULTIPLE_MANE_SELECT_CONFLICT",
                message="Multiple MANE Select transcripts were present; human review is required.",
                severity="warning",
                blocking=True,
            )
        )
    if len(canonical) > 1:
        flags.append(
            ReviewFlag(
                code="MULTIPLE_CANONICAL_CONFLICT",
                message="Multiple canonical transcripts were present; human review is required.",
                severity="warning",
                blocking=True,
            )
        )
    return flags


def _selected_safety_flags(selected: dict[str, Any]) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    if not selected.get("transcript"):
        flags.append(
            ReviewFlag(
                code="SELECTED_TRANSCRIPT_MISSING_ID",
                message="The recommended annotation lacks a transcript identifier.",
                severity="warning",
                blocking=True,
            )
        )
    if selected.get("transcript_biotype") and not selected.get("protein_coding"):
        flags.append(
            ReviewFlag(
                code="NON_CODING_TRANSCRIPT_SELECTED",
                message="The recommended transcript is non-coding; human review is required.",
                severity="warning",
                blocking=True,
            )
        )
    return flags


def _selection(
    selected: dict[str, Any],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    reason: str,
    confidence: float,
    mane_available: bool,
    canonical_available: bool,
    relevant_available: bool,
    *,
    user_transcript_provided: bool,
    user_transcript_matched: bool,
    review_flags: list[ReviewFlag],
    limitations: list[str],
    provenance: dict[str, Any],
) -> TranscriptSelection:
    return TranscriptSelection(
        selected_transcript=selected.get("transcript"),
        selected_gene=selected.get("gene"),
        selection_reason=reason,
        selection_confidence=confidence,
        candidate_transcripts=candidates,
        rejected_transcripts=rejected,
        mane_select_available=mane_available,
        canonical_available=canonical_available,
        biologically_relevant_available=relevant_available,
        user_transcript_provided=user_transcript_provided,
        user_transcript_matched=user_transcript_matched,
        review_flags=_unique_flags(review_flags),
        limitations=_unique(limitations),
        provenance=provenance,
    )


def _normalize_transcript(transcript: str) -> str:
    return transcript.split(":", 1)[0].split(".", 1)[0]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


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
