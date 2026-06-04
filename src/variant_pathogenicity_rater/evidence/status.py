from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem


class EvidenceDisplayStatus(StrEnum):
    APPLIED = "applied"
    CANDIDATE_ONLY = "candidate_only"
    REVIEW_NOTE = "review_note"
    REVIEWED_APPLIED = "reviewed_applied"
    REVIEWED_REJECTED = "reviewed_rejected"
    NEEDS_MORE_INFO = "needs_more_info"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class EvidenceWorkflowStatus(StrEnum):
    APPLIED = "applied"
    CANDIDATE_ONLY = "candidate_only"
    REVIEW_NOTE = "review_note"
    REVIEWED_APPLIED = "reviewed_applied"
    REVIEWED_REJECTED = "reviewed_rejected"
    NEEDS_MORE_INFO = "needs_more_info"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class EvidenceStatusView(SchemaModel):
    evidence_id: str | None = None
    code: str | None = None
    strength: str | None = None
    direction: str | None = None
    applied: bool | None = None
    candidate_only: bool | None = None
    requires_review: bool | None = None
    is_applied: bool = False
    is_candidate: bool = False
    is_review_note: bool = False
    is_reviewed: bool = False
    reviewed_status: str | None = None
    display_status: EvidenceDisplayStatus = EvidenceDisplayStatus.UNKNOWN
    combiner_eligible: bool = False
    reason: str = ""
    source_name: str | None = None
    provenance_summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


REVIEWED_STATUSES = {"reviewed_applied", "reviewed_rejected", "needs_more_info"}


def build_evidence_status_view(item: Any) -> EvidenceStatusView:
    payload = _payload(item)
    supporting = _dict(payload.get("supporting_data"))
    reviewed = _reviewed_payload(payload, supporting)
    reviewed_status = _reviewed_status(payload, supporting, reviewed)
    code = _text(payload.get("code") or payload.get("acmg_code"))
    strength = _text(payload.get("strength") or payload.get("suggested_strength"))
    direction = _text(payload.get("direction"))
    applied = _bool_or_none(payload.get("applied"))
    candidate_only = _bool_or_none(payload.get("candidate_only"))
    requires_review = _bool_or_none(payload.get("requires_review") if "requires_review" in payload else payload.get("requires_manual_review"))
    source = _dict(payload.get("source"))
    source_name = _text(source.get("name") or payload.get("source"))
    limitations = _limitations(payload, supporting, reviewed)

    invalid = _is_invalid_reviewed_record(payload, reviewed_status)
    is_reviewed = reviewed_status in REVIEWED_STATUSES or bool(reviewed)
    blocked_reason = _combiner_block_reason(
        payload=payload,
        supporting=supporting,
        strength=strength,
        applied=applied,
        candidate_only=candidate_only,
        reviewed_status=reviewed_status,
        invalid=invalid,
    )
    combiner_eligible = blocked_reason is None

    if invalid:
        display_status = EvidenceDisplayStatus.INVALID
    elif reviewed_status == "reviewed_applied":
        display_status = EvidenceDisplayStatus.REVIEWED_APPLIED if not combiner_eligible else EvidenceDisplayStatus.APPLIED
    elif reviewed_status == "reviewed_rejected":
        display_status = EvidenceDisplayStatus.REVIEWED_REJECTED
    elif reviewed_status == "needs_more_info":
        display_status = EvidenceDisplayStatus.NEEDS_MORE_INFO
    elif combiner_eligible:
        display_status = EvidenceDisplayStatus.APPLIED
    elif _is_review_note(payload, supporting, reviewed_status, source_name):
        display_status = EvidenceDisplayStatus.REVIEW_NOTE
    elif _candidate_signal(payload, supporting, candidate_only, applied, strength):
        display_status = EvidenceDisplayStatus.CANDIDATE_ONLY
    else:
        display_status = EvidenceDisplayStatus.UNKNOWN

    return EvidenceStatusView(
        evidence_id=_text(payload.get("evidence_id") or payload.get("source_candidate_evidence_id")),
        code=code,
        strength=strength,
        direction=direction,
        applied=applied,
        candidate_only=candidate_only,
        requires_review=requires_review,
        is_applied=display_status == EvidenceDisplayStatus.APPLIED,
        is_candidate=display_status == EvidenceDisplayStatus.CANDIDATE_ONLY,
        is_review_note=display_status
        in {
            EvidenceDisplayStatus.REVIEW_NOTE,
            EvidenceDisplayStatus.REVIEWED_REJECTED,
            EvidenceDisplayStatus.NEEDS_MORE_INFO,
        },
        is_reviewed=is_reviewed,
        reviewed_status=reviewed_status,
        display_status=display_status,
        combiner_eligible=combiner_eligible,
        reason=blocked_reason or "Evidence item is eligible for applied evidence grouping.",
        source_name=source_name,
        provenance_summary=_provenance_summary(payload, supporting, reviewed, source),
        limitations=limitations,
    )


def is_applied_evidence(item: Any) -> bool:
    return build_evidence_status_view(item).is_applied


def is_candidate_evidence(item: Any) -> bool:
    return build_evidence_status_view(item).is_candidate


def is_review_note_evidence(item: Any) -> bool:
    view = build_evidence_status_view(item)
    return view.is_review_note or (not view.is_applied)


def is_combiner_eligible(item: Any) -> bool:
    return build_evidence_status_view(item).combiner_eligible


def split_evidence_by_status(
    items: list[Any],
    reviewed_records: list[Any] | None = None,
) -> dict[str, list[Any]]:
    split = {
        "applied": [],
        "candidate": [],
        "review_note": [],
        "reviewed": list(reviewed_records or []),
        "invalid": [],
        "unknown": [],
    }
    for item in items:
        view = build_evidence_status_view(item)
        if view.is_applied:
            split["applied"].append(item)
        elif view.display_status == EvidenceDisplayStatus.INVALID:
            split["invalid"].append(item)
            split["review_note"].append(item)
        elif view.display_status == EvidenceDisplayStatus.UNKNOWN:
            split["unknown"].append(item)
            split["review_note"].append(item)
        elif view.is_review_note:
            split["review_note"].append(item)
        else:
            split["candidate"].append(item)
            split["review_note"].append(item)
    return split


def summarize_evidence_status(
    items: list[Any],
    reviewed_records: list[Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "applied": 0,
        "candidate_only": 0,
        "review_note": 0,
        "reviewed_applied": 0,
        "reviewed_rejected": 0,
        "needs_more_info": 0,
        "invalid": 0,
        "unknown": 0,
        "applied_count": 0,
        "candidate_count": 0,
        "review_note_count": 0,
        "reviewed_applied_count": 0,
        "reviewed_rejected_count": 0,
        "needs_more_info_count": 0,
        "invalid_count": 0,
        "combiner_eligible_count": 0,
        "codes_by_status": {},
    }

    for item in items:
        view = build_evidence_status_view(item)
        _increment_summary(summary, view)

    for record in reviewed_records or []:
        view = build_evidence_status_view(record)
        status = view.reviewed_status or str(view.display_status)
        if status not in REVIEWED_STATUSES and view.display_status != EvidenceDisplayStatus.INVALID:
            continue
        _increment_summary(summary, view)

    return summary


def _increment_summary(summary: dict[str, Any], view: EvidenceStatusView) -> None:
    status = str(view.display_status)
    if view.display_status == EvidenceDisplayStatus.INVALID:
        status = "invalid"
    elif view.reviewed_status in REVIEWED_STATUSES and not view.is_applied:
        status = view.reviewed_status
    summary[status] = int(summary.get(status) or 0) + 1
    count_key = {
        "applied": "applied_count",
        "candidate_only": "candidate_count",
        "review_note": "review_note_count",
        "reviewed_applied": "reviewed_applied_count",
        "reviewed_rejected": "reviewed_rejected_count",
        "needs_more_info": "needs_more_info_count",
        "invalid": "invalid_count",
    }.get(status)
    if count_key:
        summary[count_key] = int(summary.get(count_key) or 0) + 1
    if view.combiner_eligible:
        summary["combiner_eligible_count"] = int(summary["combiner_eligible_count"]) + 1
    if view.code:
        codes = summary.setdefault("codes_by_status", {}).setdefault(status, [])
        if view.code not in codes:
            codes.append(view.code)


def _combiner_block_reason(
    *,
    payload: dict[str, Any],
    supporting: dict[str, Any],
    strength: str | None,
    applied: bool | None,
    candidate_only: bool | None,
    reviewed_status: str | None,
    invalid: bool,
) -> str | None:
    if invalid:
        return "Invalid reviewed evidence is not combiner eligible."
    if reviewed_status in {"reviewed_rejected", "needs_more_info"}:
        return f"Reviewed evidence status {reviewed_status} is not combiner eligible."
    if payload.get("candidate_code") or str(payload.get("code") or "").endswith("_candidate"):
        return "Literature or suggested candidate evidence is not combiner eligible."
    if candidate_only is True:
        return "candidate_only=true is not combiner eligible."
    if strength == "none":
        return "strength=none is not combiner eligible."
    if applied is False:
        return "applied=false is not combiner eligible."
    if supporting.get("candidate_only") is True:
        return "supporting_data.candidate_only=true is not combiner eligible."
    if supporting.get("applied") is False:
        return "supporting_data.applied=false is not combiner eligible."
    if supporting.get("evidence_status") == "candidate":
        return "supporting_data.evidence_status=candidate is not combiner eligible."
    if reviewed_status == "reviewed_applied":
        if not payload.get("evidence_id") or not isinstance(payload.get("source"), dict):
            return "Raw reviewed_applied records are not combiner eligible until converted into EvidenceItem."
        return None
    if not payload.get("evidence_id") and not isinstance(payload.get("source"), dict):
        return "Unrecognized evidence-like record is not combiner eligible."
    return None


def _is_review_note(
    payload: dict[str, Any],
    supporting: dict[str, Any],
    reviewed_status: str | None,
    source_name: str | None,
) -> bool:
    if reviewed_status in {"reviewed_rejected", "needs_more_info"}:
        return True
    if supporting.get("review_note") or supporting.get("reviewed_evidence"):
        return True
    if source_name in {"ClinVar", "ClinGen Evidence Repository", "manual_reviewed_evidence"}:
        return True
    return bool(payload.get("review_notes"))


def _candidate_signal(
    payload: dict[str, Any],
    supporting: dict[str, Any],
    candidate_only: bool | None,
    applied: bool | None,
    strength: str | None,
) -> bool:
    return bool(
        candidate_only
        or applied is False
        or strength == "none"
        or supporting.get("candidate_only")
        or supporting.get("evidence_status") == "candidate"
        or payload.get("candidate_code")
        or str(payload.get("code") or "").endswith("_candidate")
    )


def _reviewed_payload(payload: dict[str, Any], supporting: dict[str, Any]) -> dict[str, Any]:
    reviewed = _dict(supporting.get("reviewed_evidence"))
    return reviewed or _dict(payload.get("reviewed_evidence"))


def _reviewed_status(
    payload: dict[str, Any],
    supporting: dict[str, Any],
    reviewed: dict[str, Any],
) -> str | None:
    status = payload.get("evidence_status") or supporting.get("evidence_status") or reviewed.get("evidence_status")
    if status is None and payload.get("status") in REVIEWED_STATUSES:
        status = payload.get("status")
    return _text(status)


def _is_invalid_reviewed_record(payload: dict[str, Any], reviewed_status: str | None) -> bool:
    if payload.get("invalid") is True or payload.get("validation_status") == "invalid":
        return True
    if reviewed_status == "reviewed_applied":
        strength = _text(payload.get("strength"))
        direction = _text(payload.get("direction"))
        if strength == "none" or direction in {"neutral", "conflicting"}:
            return True
        if not (payload.get("rationale") or payload.get("review_date")) and not payload.get("evidence_id"):
            return True
    return False


def _provenance_summary(
    payload: dict[str, Any],
    supporting: dict[str, Any],
    reviewed: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    provenance = _dict(source.get("provenance")) or _dict(supporting.get("provenance")) or _dict(reviewed.get("provenance")) or _dict(payload.get("provenance"))
    return {
        key: value
        for key, value in {
            "source_version": provenance.get("source_version") or source.get("version"),
            "retrieval_timestamp": provenance.get("retrieved_at") or source.get("retrieval_timestamp"),
            "query": provenance.get("query") or source.get("query"),
            "raw_record_hash": provenance.get("raw_record_hash") or source.get("raw_snapshot_ref"),
            "source_candidate_evidence_id": supporting.get("source_candidate_evidence_id")
            or reviewed.get("source_candidate_evidence_id")
            or payload.get("source_candidate_evidence_id"),
        }.items()
        if value is not None
    }


def _limitations(payload: dict[str, Any], supporting: dict[str, Any], reviewed: dict[str, Any]) -> list[str]:
    return _unique(
        [
            *list(payload.get("limitations") or []),
            *list(supporting.get("limitations") or []),
            *list(reviewed.get("limitations") or []),
        ]
    )


def _payload(item: Any) -> dict[str, Any]:
    if isinstance(item, EvidenceItem):
        return item.model_dump(mode="json")
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return dict(item)
    return {}


def _dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value if isinstance(value, dict) else {}


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _unique(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique
