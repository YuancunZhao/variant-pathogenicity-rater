from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


def create_reviewed_evidence_draft_from_literature_assessment(
    literature_assessment: dict[str, Any],
    *,
    suggested_evidence: dict[str, Any] | None = None,
    review_questions: list[str] | None = None,
    index: int = 0,
) -> dict[str, Any]:
    """Create a human-curation draft from one literature assessment.

    The draft is intentionally not a ready-to-apply reviewed evidence record:
    curator fields are blank/pending and evidence_status starts as
    needs_more_info. A curator must edit it into the strict reviewed_evidence
    schema and explicitly set reviewed_applied before rate_variant can promote it.
    """

    source_candidate_evidence_id = _source_candidate_evidence_id(
        literature_assessment,
        suggested_evidence,
        index,
    )
    acmg_code = _base_acmg_code(
        _first_string(
            literature_assessment.get("acmg_code"),
            literature_assessment.get("candidate_code"),
            suggested_evidence.get("code") if suggested_evidence else None,
        )
    )
    suggested_strength = _first_string(
        literature_assessment.get("suggested_strength"),
        suggested_evidence.get("strength") if suggested_evidence else None,
        "none",
    )
    extracted_claims = _string_list(
        literature_assessment.get("extracted_claims")
        or literature_assessment.get("extracted_claim")
        or []
    )
    extracted_claim = "\n".join(extracted_claims)
    reason_not_applied = _first_string(
        literature_assessment.get("reason_not_applied"),
        suggested_evidence.get("reason_not_applied") if suggested_evidence else None,
        "Suggested literature evidence is not automatically applied to ACMG classification.",
    )
    rationale_parts = [part for part in [extracted_claim, reason_not_applied] if part]
    pmid = _first_string(
        literature_assessment.get("pmid"),
        suggested_evidence.get("pmid") if suggested_evidence else None,
    )
    doi = _first_string(
        literature_assessment.get("doi"),
        suggested_evidence.get("doi") if suggested_evidence else None,
    )
    citation = _first_string(
        literature_assessment.get("citation"),
        suggested_evidence.get("citation") if suggested_evidence else None,
        f"PMID:{pmid}" if pmid else None,
        doi,
    )

    return {
        "source_candidate_evidence_id": source_candidate_evidence_id,
        "acmg_code": acmg_code,
        "suggested_strength": suggested_strength,
        "strength": suggested_strength,
        "direction": _direction_for_code(acmg_code),
        "curator_decision": "pending",
        "curator_name": "",
        "review_date": "",
        "rationale": "\n\n".join(rationale_parts),
        "citation": citation,
        "pmid": pmid,
        "doi": doi,
        "extracted_claim": extracted_claim,
        "review_questions": review_questions or [],
        "provenance": {
            "draft_source": "acmg_literature_evidence_agent",
            "source_candidate_evidence_id": source_candidate_evidence_id,
            "literature_assessment": literature_assessment,
            "suggested_evidence": suggested_evidence or {},
            "pmid": pmid,
            "doi": doi,
            "extracted_claim": extracted_claim,
            "review_questions": review_questions or [],
            **_dict_or_empty(literature_assessment.get("provenance")),
        },
        "override_reason": "",
        "evidence_status": "needs_more_info",
        "requires_manual_review": True,
        "audit_trail": [],
    }


def create_reviewed_evidence_drafts(literature_assessment_json: Any) -> dict[str, Any]:
    """Convert an assess_literature_evidence result into review draft records."""

    payload = _coerce_payload(literature_assessment_json)
    if not isinstance(payload, dict):
        return _structured_error("literature assessment payload must be a JSON object.")

    assessments = payload.get("literature_evidence_assessments")
    if not isinstance(assessments, list):
        return _structured_error("literature_evidence_assessments must be a list.")

    suggested_items = payload.get("suggested_evidence") or []
    if not isinstance(suggested_items, list):
        return _structured_error("suggested_evidence must be a list when present.")

    review_questions = _string_list(payload.get("review_questions") or [])
    drafts: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, assessment in enumerate(assessments):
        if not isinstance(assessment, dict):
            errors.append({"index": index, "message": "assessment must be an object."})
            continue
        suggested = suggested_items[index] if index < len(suggested_items) else None
        if suggested is not None and not isinstance(suggested, dict):
            errors.append({"index": index, "message": "suggested_evidence item must be an object."})
            suggested = None
        drafts.append(
            create_reviewed_evidence_draft_from_literature_assessment(
                assessment,
                suggested_evidence=suggested,
                review_questions=review_questions,
                index=index,
            )
        )

    status = "error" if errors and not drafts else "ok"
    return {
        "status": status,
        "tool": "create_reviewed_evidence_draft",
        "stage": "literature_suggested_to_reviewed_draft",
        "reviewed_evidence": drafts,
        "reviewed_evidence_drafts": drafts,
        "errors": errors,
        "limitations": [
            "Drafts are not applied evidence.",
            "A curator must explicitly set evidence_status to reviewed_applied "
            "before rate_variant can apply a reviewed record.",
            "Draft template metadata fields may need to be removed or moved into "
            "provenance before using --reviewed-evidence.",
        ],
        "human_review": {
            "required": True,
            "notice": (
                "Suggested literature evidence is converted only into a manual "
                "reviewed_evidence draft."
            ),
        },
        "final_classification_changed": False,
        "applied_evidence": [],
    }


def _source_candidate_evidence_id(
    assessment: dict[str, Any],
    suggested: dict[str, Any] | None,
    index: int,
) -> str:
    explicit = _first_string(
        assessment.get("source_candidate_evidence_id"),
        suggested.get("source_candidate_evidence_id") if suggested else None,
        suggested.get("evidence_id") if suggested else None,
        _dict_or_empty(assessment.get("provenance")).get("record_id"),
    )
    if explicit:
        return explicit
    fingerprint = {
        "index": index,
        "candidate_code": assessment.get("candidate_code") or assessment.get("acmg_code"),
        "citation": assessment.get("citation"),
        "pmid": assessment.get("pmid"),
        "doi": assessment.get("doi"),
        "claims": assessment.get("extracted_claims") or assessment.get("extracted_claim"),
    }
    digest = sha256(json.dumps(fingerprint, sort_keys=True, default=str).encode()).hexdigest()[:12]
    base_code = _base_acmg_code(str(fingerprint["candidate_code"] or "ACMG"))
    return f"literature-suggested-{base_code}-{digest}"


def _base_acmg_code(value: str | None) -> str:
    return str(value or "ACMG").removesuffix("_candidate")


def _direction_for_code(code: str) -> str:
    return "benign" if code.startswith(("BA", "BS", "BP")) else "pathogenic"


def _coerce_payload(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _structured_error(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "tool": "create_reviewed_evidence_draft",
        "stage": "literature_suggested_to_reviewed_draft",
        "reviewed_evidence": [],
        "reviewed_evidence_drafts": [],
        "errors": [{"message": message}],
        "limitations": [
            "No reviewed evidence draft was generated.",
            "No suggested literature evidence was applied or used for classification.",
        ],
        "human_review": {"required": True},
        "final_classification_changed": False,
        "applied_evidence": [],
    }


def _first_string(*values: Any) -> str | None:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [str(value)]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
