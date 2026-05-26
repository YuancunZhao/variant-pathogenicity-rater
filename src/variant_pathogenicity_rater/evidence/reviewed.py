from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import (
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.reviewed import (
    ReviewedEvidence,
    ReviewedEvidenceResult,
    ReviewedEvidenceStatus,
)
from variant_pathogenicity_rater.schemas.variant import Variant


def process_reviewed_evidence(
    raw_reviewed_evidence: Any,
    existing_evidence_items: list[EvidenceItem],
    variant: Variant,
) -> ReviewedEvidenceResult:
    records, limitations, flags = _parse_records(raw_reviewed_evidence)
    applied_items: list[EvidenceItem] = []
    review_note_items: list[EvidenceItem] = []
    known_ids = {item.evidence_id for item in existing_evidence_items}

    for record in records:
        if record.source_candidate_evidence_id and record.source_candidate_evidence_id not in known_ids:
            limitations.append(
                "Reviewed evidence references source_candidate_evidence_id "
                f"{record.source_candidate_evidence_id}, but no matching candidate item was found."
            )
            flags.append(
                ReviewFlag(
                    code="REVIEWED_SOURCE_CANDIDATE_NOT_FOUND",
                    message=(
                        "Reviewed evidence linked to a candidate evidence ID that was not present "
                        "in this run; traceability requires manual review."
                    ),
                    severity="warning",
                    blocking=False,
                )
            )

        if record.evidence_status == ReviewedEvidenceStatus.REVIEWED_APPLIED:
            item = _applied_item(record, variant)
            applied_items.append(item)
            flags.extend(_conflict_flags(item, existing_evidence_items + applied_items[:-1]))
            continue

        review_note_items.append(_review_note_item(record, variant))

    return ReviewedEvidenceResult(
        applied_items=applied_items,
        review_note_items=review_note_items,
        review_flags=_unique_flags(flags),
        limitations=_unique(limitations),
        reviewed_evidence_records=[record.model_dump(mode="json") for record in records],
    )


def _parse_records(raw: Any) -> tuple[list[ReviewedEvidence], list[str], list[ReviewFlag]]:
    if raw is None:
        return [], [], []
    payload = raw.get("reviewed_evidence") if isinstance(raw, dict) else raw
    if not isinstance(payload, list):
        return [], ["reviewed_evidence must be a list or an object containing reviewed_evidence."], [
            _invalid_flag("reviewed_evidence must be a list.")
        ]

    records: list[ReviewedEvidence] = []
    limitations: list[str] = []
    flags: list[ReviewFlag] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            limitations.append(f"reviewed_evidence[{index}] must be an object.")
            flags.append(_invalid_flag(f"reviewed_evidence[{index}] must be an object."))
            continue
        try:
            records.append(ReviewedEvidence.model_validate(item))
        except ValidationError as exc:
            limitations.append(f"reviewed_evidence[{index}] validation failed: {exc}")
            flags.append(_invalid_flag(f"reviewed_evidence[{index}] validation failed."))
    return records, limitations, flags


def _applied_item(record: ReviewedEvidence, variant: Variant) -> EvidenceItem:
    reviewed = record.model_dump(mode="json")
    return EvidenceItem(
        evidence_id=_evidence_id(record, variant, "applied"),
        code=record.acmg_code,
        strength=record.strength,
        direction=record.direction,
        reason=record.rationale,
        source=_source(record, variant),
        confidence=0.95,
        requires_review=True,
        candidate_only=False,
        applied=True,
        triggered_by=["manual_reviewed_evidence"],
        supporting_data={
            "reviewed_evidence": reviewed,
            "source_candidate_evidence_id": record.source_candidate_evidence_id,
            "evidence_status": _value(ReviewedEvidenceStatus.REVIEWED_APPLIED),
            "curator_decision": record.curator_decision,
            "curator_name": record.curator_name,
            "review_date": record.review_date.isoformat(),
            "override_reason": record.override_reason,
            "citation": record.citation,
            "provenance": record.provenance,
            "requires_manual_review": True,
        },
        audit_trail=[*record.audit_trail, _audit("manual_reviewed_evidence_promoted", record)],
    )


def _review_note_item(record: ReviewedEvidence, variant: Variant) -> EvidenceItem:
    reviewed = record.model_dump(mode="json")
    return EvidenceItem(
        evidence_id=_evidence_id(record, variant, "review-note"),
        code=record.acmg_code,
        strength=EvidenceStrength.NONE,
        direction=record.direction,
        reason=record.rationale,
        source=_source(record, variant),
        confidence=0.0,
        requires_review=True,
        candidate_only=True,
        applied=False,
        triggered_by=["manual_reviewed_evidence"],
        supporting_data={
            "reviewed_evidence": reviewed,
            "source_candidate_evidence_id": record.source_candidate_evidence_id,
            "candidate_only": True,
            "applied": False,
            "evidence_status": _value(record.evidence_status),
            "curator_decision": record.curator_decision,
            "curator_name": record.curator_name,
            "review_date": record.review_date.isoformat(),
            "override_reason": record.override_reason,
            "citation": record.citation,
            "provenance": record.provenance,
            "requires_manual_review": True,
        },
        audit_trail=[*record.audit_trail, _audit("manual_reviewed_evidence_retained_as_review_note", record)],
    )


def _source(record: ReviewedEvidence, variant: Variant) -> EvidenceSource:
    return EvidenceSource(
        name="manual_reviewed_evidence",
        version="reviewed-evidence-v1",
        retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
        query={
            "variant_id": variant.variant_id,
            "source_candidate_evidence_id": record.source_candidate_evidence_id,
            "acmg_code": str(record.acmg_code),
            "evidence_status": _value(record.evidence_status),
        },
        provenance=record.provenance,
    )


def _conflict_flags(item: EvidenceItem, existing_items: list[EvidenceItem]) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    for existing in existing_items:
        if not _is_applied(existing) or str(existing.code) != str(item.code):
            continue
        if str(existing.direction) != str(item.direction):
            flags.append(
                ReviewFlag(
                    code="REVIEWED_EVIDENCE_DIRECTION_CONFLICT",
                    message=(
                        f"Reviewed {item.code} evidence conflicts with existing applied "
                        f"{existing.code} evidence direction."
                    ),
                    severity="error",
                    blocking=True,
                )
            )
        elif str(existing.strength) != str(item.strength):
            flags.append(
                ReviewFlag(
                    code="REVIEWED_EVIDENCE_STRENGTH_CONFLICT",
                    message=(
                        f"Reviewed {item.code} evidence uses strength {item.strength}, "
                        f"but existing applied evidence uses {existing.strength}."
                    ),
                    severity="error",
                    blocking=True,
                )
            )
    return flags


def _is_applied(item: EvidenceItem) -> bool:
    return not (
        item.candidate_only
        or item.applied is False
        or str(item.strength) == EvidenceStrength.NONE.value
        or item.supporting_data.get("candidate_only")
        or item.supporting_data.get("evidence_status") == "candidate"
        or item.supporting_data.get("applied") is False
    )


def _evidence_id(record: ReviewedEvidence, variant: Variant, status: str) -> str:
    payload = {
        "variant": variant.variant_id,
        "code": str(record.acmg_code),
        "strength": str(record.strength),
        "direction": str(record.direction),
        "status": _value(record.evidence_status),
        "source_candidate_evidence_id": record.source_candidate_evidence_id,
        "rationale": record.rationale,
        "citation": record.citation,
    }
    digest = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"reviewed-{record.acmg_code}-{digest}" if status == "applied" else f"reviewed-note-{record.acmg_code}-{digest}"


def _audit(event_type: str, record: ReviewedEvidence) -> AuditTrail:
    return AuditTrail(
        event_id=f"audit-{event_type}-{datetime.now(timezone.utc).timestamp():.6f}",
        event_type=event_type,
        actor=record.curator_name or "curator",
        tool_name="process_reviewed_evidence",
        query={"source_candidate_evidence_id": record.source_candidate_evidence_id},
        notes=[record.curator_decision],
    )


def _invalid_flag(message: str) -> ReviewFlag:
    return ReviewFlag(
        code="INVALID_REVIEWED_EVIDENCE",
        message=message,
        severity="error",
        blocking=True,
    )


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _unique_flags(flags: list[ReviewFlag]) -> list[ReviewFlag]:
    seen: set[tuple[str, str]] = set()
    unique: list[ReviewFlag] = []
    for flag in flags:
        key = (flag.code, flag.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(flag)
    return unique
