from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import ValidationError

from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.transcript_support.schema import (
    CanonicalTranscript,
    TranscriptMetadata,
    TranscriptValidationResult,
    TranscriptValidationStatus,
)


TRANSCRIPT_RE = re.compile(r"^(?P<accession>[A-Z]{2,4}_?\d+)(?:\.(?P<version>\d+))?$")
PROTEIN_PREFIX_RE = re.compile(r"^(?P<accession>[A-Z]{1,3}_\d+(?:\.\d+)?):")
DEPRECATED_STATUSES = {"deprecated", "retired", "withdrawn", "obsolete", "replaced"}
MANE_SELECT_VALUES = {"mane_select", "select", "mane select", "mane_select_clinical"}


def canonicalize_transcript(value: str | None) -> CanonicalTranscript:
    raw = (value or "").strip() or None
    if raw and ":" in raw:
        raw = raw.split(":", 1)[0]
    match = TRANSCRIPT_RE.match(raw or "")
    accession = match.group("accession") if match else raw
    version = match.group("version") if match else None
    return CanonicalTranscript(
        raw=raw,
        accession=accession,
        version=version,
        source_family=_source_family(accession),
    )


def load_transcript_metadata_records(raw: Any) -> tuple[list[TranscriptMetadata], list[str]]:
    """Load local transcript metadata from a list, JSON array, or JSONL text."""

    if raw is None:
        return [], []
    limitations: list[str] = []
    payload: Any
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return [], []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = []
            for index, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    limitations.append(f"Malformed transcript metadata JSONL line {index}: {exc}")
    else:
        payload = raw
    if isinstance(payload, dict):
        payload = payload.get("records") or payload.get("transcripts") or []
    if not isinstance(payload, list):
        return [], ["Transcript metadata fixture must be a list, JSON array, JSONL text, or object with records."]

    records: list[TranscriptMetadata] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            limitations.append(f"Transcript metadata record {index} is not an object.")
            continue
        try:
            records.append(TranscriptMetadata.model_validate(item))
        except ValidationError as exc:
            limitations.append(f"Malformed transcript metadata record {index}: {exc.__class__.__name__}: {exc}")
    return records, _unique(limitations)


def validate_transcript_metadata(
    *,
    variant: Variant,
    context: GeneDiseaseContext | None = None,
    annotation_records: list[VariantAnnotation] | None = None,
    transcript_selection: TranscriptSelection | None = None,
    transcript_records: Iterable[TranscriptMetadata] | None = None,
    provider_limitations: list[str] | None = None,
) -> TranscriptValidationResult:
    records = list(transcript_records or [])
    annotations = annotation_records or []
    flags: list[ReviewFlag] = []
    limitations = list(provider_limitations or [])
    provenance: dict[str, Any] = {
        "validator": "local_transcript_validation_v1",
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "scope": "transcript validation only; not ACMG evidence",
    }

    input_transcript = _input_transcript(variant, context, transcript_selection)
    normalized = canonicalize_transcript(input_transcript)
    user_transcript_provided = bool(input_transcript)
    gene = (variant.gene_symbol or (context.gene_symbol if context else None) or "").upper()
    build = str(variant.genome_build)
    gene_records = [record for record in records if record.gene.upper() == gene] if gene else records
    mane_candidates = [_summary(record) for record in gene_records if _is_mane_select(record)]
    canonical_candidates = [_summary(record) for record in gene_records if record.canonical]
    matched_record = _match_record(normalized, gene_records)

    if not records:
        limitations.append("No local transcript metadata fixture was supplied.")
    elif gene and not gene_records:
        limitations.append("Local transcript metadata fixture has no records for the input gene.")

    if not input_transcript:
        _select_recommendation_only(flags, limitations, mane_candidates, canonical_candidates)
    elif matched_record is None:
        flags.append(_flag(
            "USER_TRANSCRIPT_NOT_IN_TRANSCRIPT_FIXTURE",
            "User/input transcript was not present in local transcript metadata; no transcript was automatically substituted.",
            True,
        ))
        limitations.append("User/input transcript was not present in local transcript metadata.")
    else:
        _check_version(normalized, matched_record, flags, limitations)
        _check_record_safety(matched_record, build, flags, limitations)
        _check_mane_recommendation(input_transcript, matched_record, mane_candidates, flags)

    protein_expected = matched_record.protein_accession if matched_record else None
    protein_observed = _protein_accession_from_hgvs_p(variant.hgvs_p)
    protein_match: bool | None = None
    if protein_expected and protein_observed:
        protein_match = protein_expected == protein_observed
        if not protein_match:
            flags.append(_flag(
                "TRANSCRIPT_PROTEIN_ACCESSION_MISMATCH",
                "Protein accession from HGVS p. does not match local transcript metadata.",
                True,
            ))
            limitations.append("Transcript/protein accession mismatch requires review.")
    elif protein_expected or protein_observed:
        protein_match = None

    for annotation in annotations:
        if annotation.transcript and input_transcript:
            ann = canonicalize_transcript(annotation.transcript)
            if ann.accession and normalized.accession and ann.accession != normalized.accession:
                flags.append(_flag(
                    "TRANSCRIPT_METADATA_ANNOTATION_MISMATCH",
                    "Annotation transcript differs from user/input transcript.",
                    True,
                ))
                limitations.append("Annotation transcript differs from user/input transcript.")

    status = _status(flags, limitations, matched_record, records)
    return TranscriptValidationResult(
        status=status,
        input_transcript=input_transcript,
        normalized_input=normalized,
        matched_record=_summary(matched_record) if matched_record else None,
        mane_select_candidates=mane_candidates,
        canonical_candidates=canonical_candidates,
        protein_accession_match=protein_match,
        protein_accession_expected=protein_expected,
        protein_accession_observed=protein_observed,
        user_transcript_provided=user_transcript_provided,
        user_transcript_preserved=True,
        review_flags=_unique_flags(flags),
        limitations=_unique(limitations),
        provenance=provenance,
    )


def _input_transcript(
    variant: Variant,
    context: GeneDiseaseContext | None,
    selection: TranscriptSelection | None,
) -> str | None:
    if variant.transcript is not None:
        return f"{variant.transcript.accession}.{variant.transcript.version}" if variant.transcript.version else variant.transcript.accession
    if context and context.transcript is not None:
        return f"{context.transcript.accession}.{context.transcript.version}" if context.transcript.version else context.transcript.accession
    if selection and selection.selected_transcript:
        return selection.selected_transcript
    return None


def _source_family(accession: str | None) -> str:
    if not accession:
        return "unknown"
    if accession.startswith(("NM_", "NR_", "XM_", "XR_")):
        return "refseq"
    if accession.startswith("ENST"):
        return "ensembl"
    return "unknown"


def _match_record(
    normalized: CanonicalTranscript,
    records: list[TranscriptMetadata],
) -> TranscriptMetadata | None:
    exact: list[TranscriptMetadata] = []
    base: list[TranscriptMetadata] = []
    for record in records:
        record_norm = canonicalize_transcript(record.transcript)
        if record_norm.accession != normalized.accession:
            continue
        if normalized.version and record.transcript_version == normalized.version:
            exact.append(record)
        else:
            base.append(record)
    return exact[0] if exact else (base[0] if base else None)


def _check_version(
    normalized: CanonicalTranscript,
    record: TranscriptMetadata,
    flags: list[ReviewFlag],
    limitations: list[str],
) -> None:
    if normalized.version and record.transcript_version and normalized.version != record.transcript_version:
        flags.append(_flag(
            "TRANSCRIPT_VERSION_MISMATCH",
            "Transcript accession matched but transcript version differs from local metadata.",
            True,
        ))
        limitations.append("Transcript version mismatch requires review.")


def _check_record_safety(
    record: TranscriptMetadata,
    genome_build: str,
    flags: list[ReviewFlag],
    limitations: list[str],
) -> None:
    if record.genome_build != genome_build:
        flags.append(_flag(
            "TRANSCRIPT_GENOME_BUILD_MISMATCH",
            "Local transcript metadata genome build differs from input genome build.",
            True,
        ))
        limitations.append("Transcript metadata genome build mismatch requires review.")
    if not record.protein_coding:
        flags.append(_flag(
            "NON_CODING_TRANSCRIPT_METADATA",
            "Local transcript metadata marks the transcript as non-coding.",
            True,
        ))
        limitations.append("Non-coding transcript metadata blocks applied transcript-dependent evidence.")
    if record.transcript_status.strip().lower() in DEPRECATED_STATUSES:
        flags.append(_flag(
            "DEPRECATED_TRANSCRIPT_METADATA",
            "Local transcript metadata marks the transcript as deprecated or retired.",
            True,
        ))
        limitations.append("Deprecated transcript metadata blocks confident transcript-dependent evidence.")
    if not record.source_version:
        limitations.append("Transcript metadata source_version is missing.")


def _check_mane_recommendation(
    input_transcript: str,
    matched_record: TranscriptMetadata,
    mane_candidates: list[dict[str, Any]],
    flags: list[ReviewFlag],
) -> None:
    if _is_mane_select(matched_record):
        flags.append(_flag(
            "MANE_SELECT_TRANSCRIPT_SUPPORTED",
            "User/input transcript matches a local MANE Select transcript record.",
            False,
            severity="info",
        ))
        return
    normalized_input = canonicalize_transcript(input_transcript)
    for candidate in mane_candidates:
        candidate_norm = canonicalize_transcript(candidate.get("transcript"))
        if candidate_norm.accession != normalized_input.accession:
            flags.append(_flag(
                "MANE_SELECT_DIFFERS_FROM_USER_TRANSCRIPT",
                "A MANE Select transcript is available but differs from the user/input transcript; it is recommendation context only.",
                True,
            ))
            return


def _select_recommendation_only(
    flags: list[ReviewFlag],
    limitations: list[str],
    mane_candidates: list[dict[str, Any]],
    canonical_candidates: list[dict[str, Any]],
) -> None:
    if mane_candidates:
        flags.append(_flag(
            "MANE_SELECT_TRANSCRIPT_RECOMMENDED",
            "MANE Select transcript is available as recommendation context only.",
            False,
            severity="info",
        ))
    elif canonical_candidates:
        flags.append(_flag(
            "CANONICAL_TRANSCRIPT_RECOMMENDED",
            "Canonical transcript is available as recommendation context only.",
            False,
            severity="info",
        ))
    else:
        limitations.append("No user transcript and no MANE/canonical transcript recommendation were available.")


def _is_mane_select(record: TranscriptMetadata) -> bool:
    status = (record.mane_status or "").strip().lower().replace("-", "_")
    tags = {tag.strip().lower().replace("-", "_") for tag in record.tags}
    return status in MANE_SELECT_VALUES or "mane_select" in tags


def _protein_accession_from_hgvs_p(value: str | None) -> str | None:
    if not value:
        return None
    match = PROTEIN_PREFIX_RE.match(value.strip())
    return match.group("accession") if match else None


def _summary(record: TranscriptMetadata | None) -> dict[str, Any]:
    if record is None:
        return {}
    return record.model_dump(mode="json")


def _status(
    flags: list[ReviewFlag],
    limitations: list[str],
    matched_record: TranscriptMetadata | None,
    records: list[TranscriptMetadata],
) -> TranscriptValidationStatus:
    if any(flag.blocking for flag in flags):
        return "conflict"
    if any(flag.severity == "warning" for flag in flags):
        return "warning"
    if not records or matched_record is None:
        return "insufficient"
    if limitations:
        return "warning"
    return "ok"


def _flag(code: str, message: str, blocking: bool, *, severity: str | None = None) -> ReviewFlag:
    return ReviewFlag(
        code=code,
        message=message,
        severity=severity or ("error" if blocking else "warning"),
        blocking=blocking,
    )


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
