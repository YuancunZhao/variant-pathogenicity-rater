from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.config.thresholds import (
    ComputationalEvidenceThresholds,
    PopulationRuleThresholds,
)
from variant_pathogenicity_rater.pvs1.schema import PVS1Decision
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem, EvidenceStrength
from variant_pathogenicity_rater.vcep_profiles.schema import VCEPOverrideContext, profile_summary


PVS1_STRENGTH_ORDER = {
    "not_applicable": 0,
    "PVS1_candidate": 0,
    "PVS1_Supporting": 1,
    "PVS1_Moderate": 2,
    "PVS1_Strong": 3,
    "PVS1": 4,
}

PVS1_ITEM_STRENGTH = {
    "PVS1_Supporting": EvidenceStrength.SUPPORTING,
    "PVS1_Moderate": EvidenceStrength.MODERATE,
    "PVS1_Strong": EvidenceStrength.STRONG,
    "PVS1": EvidenceStrength.VERY_STRONG,
}


def vcep_override_metadata(context: VCEPOverrideContext | None) -> dict[str, Any] | None:
    if context is None or context.active_profile is None:
        return None
    profile = context.active_profile
    return {
        "profile": profile_summary(profile),
        "override_enabled": context.override_enabled,
        "override_applied": context.applied,
        "blocked_reasons": list(context.blocked_reasons),
        "citations": list(profile.citations),
        "provenance": dict(profile.provenance),
    }


def apply_population_threshold_overrides(
    thresholds: PopulationRuleThresholds,
    context: VCEPOverrideContext | None,
) -> PopulationRuleThresholds:
    if context is None or not context.applied or not context.population_threshold_overrides:
        return thresholds
    payload = thresholds.model_dump(mode="json")
    for key, value in context.population_threshold_overrides.items():
        if key in payload:
            payload[key] = value
    payload["disease_specific"] = True
    return PopulationRuleThresholds.model_validate(payload)


def apply_computational_threshold_overrides(
    thresholds: ComputationalEvidenceThresholds,
    context: VCEPOverrideContext | None,
) -> ComputationalEvidenceThresholds:
    if context is None or not context.applied:
        return thresholds
    overrides = context.computational_overrides.get("thresholds") or context.computational_overrides
    if not isinstance(overrides, dict):
        return thresholds
    payload = thresholds.model_dump(mode="json")
    for key, value in overrides.items():
        if key in payload:
            payload[key] = _stricter_computational_value(key, payload[key], value)
    return ComputationalEvidenceThresholds.model_validate(payload)


def apply_pvs1_overrides(
    item: EvidenceItem | None,
    decision: PVS1Decision,
    context: VCEPOverrideContext | None,
) -> tuple[EvidenceItem | None, PVS1Decision]:
    if context is None or not context.applied or not context.pvs1_overrides:
        return item, decision
    metadata = vcep_override_metadata(context) or {}
    overrides = context.pvs1_overrides
    notes: list[str] = []

    if overrides.get("disable") is True:
        notes.append("PVS1 disabled by approved VCEP profile override.")
        decision.applied = False
        decision.candidate_only = True
        decision.blocking_reasons = _unique([*decision.blocking_reasons, *notes])
        decision.limitations = _unique([*decision.limitations, *notes])
        if item is not None:
            item.supporting_data["pvs1_decision"] = decision.model_dump(mode="json")
            item.supporting_data["blocking_reasons"] = list(decision.blocking_reasons)
            item.supporting_data["limitations"] = list(decision.limitations)
            _make_candidate_only(item, "; ".join(notes), metadata)
        return item, decision

    max_strength = overrides.get("max_strength")
    if isinstance(max_strength, str) and _downgrade_needed(decision.strength, max_strength):
        notes.append(f"PVS1 strength capped at {max_strength} by approved VCEP profile override.")
        decision.strength = max_strength  # type: ignore[assignment]
        decision.recommended_code = max_strength
        decision.downgrade_reasons = _unique([*decision.downgrade_reasons, *notes])
        if item is not None:
            item.strength = PVS1_ITEM_STRENGTH.get(max_strength, EvidenceStrength.NONE)
            item.supporting_data["applied_pvs1_level"] = max_strength if decision.applied else None
            item.supporting_data["pvs1_decision"] = decision.model_dump(mode="json")

    if overrides.get("require_review") is True:
        notes.append("Approved VCEP profile requires focused PVS1 review.")
        decision.limitations = _unique([*decision.limitations, notes[-1]])
        if item is not None:
            item.review_flags = _append_flag(
                item.review_flags,
                "VCEP_PVS1_REVIEW_REQUIRED",
                "Approved VCEP profile requires focused PVS1 review.",
            )

    if item is not None:
        _attach_metadata(item, metadata, applied=True, notes=notes)
    return item, decision


def apply_ps1_pm5_overrides(
    items: list[EvidenceItem],
    context: VCEPOverrideContext | None,
) -> list[EvidenceItem]:
    if context is None or not context.applied or not context.ps1_pm5_overrides:
        return items
    metadata = vcep_override_metadata(context) or {}
    require_candidate_only = bool(context.ps1_pm5_overrides.get("candidate_only_required"))
    review_note = str(context.ps1_pm5_overrides.get("review_note") or "Approved VCEP profile requires PS1/PM5 review.")
    for item in items:
        if str(item.code) not in {"PS1", "PM5"}:
            continue
        if require_candidate_only:
            _make_candidate_only(item, review_note, metadata)
        else:
            _attach_metadata(item, metadata, applied=True, notes=[review_note])
        item.review_flags = _append_flag(item.review_flags, "VCEP_PS1_PM5_REVIEW_REQUIRED", review_note)
    return items


def apply_disabled_criteria(
    items: list[EvidenceItem],
    context: VCEPOverrideContext | None,
) -> list[EvidenceItem]:
    if context is None or not context.applied or not context.disabled_criteria:
        return items
    disabled = {str(code) for code in context.disabled_criteria}
    metadata = vcep_override_metadata(context) or {}
    for item in items:
        if str(item.code) in disabled:
            _make_candidate_only(
                item,
                f"{item.code} disabled by approved VCEP profile override.",
                metadata,
            )
    return items


def attach_computational_override_note(
    items: list[EvidenceItem],
    context: VCEPOverrideContext | None,
) -> list[EvidenceItem]:
    if context is None or not context.applied or not context.computational_overrides:
        return items
    note = str(
        context.computational_overrides.get("note")
        or "Approved VCEP profile computational threshold note requires review."
    )
    metadata = vcep_override_metadata(context) or {}
    for item in items:
        if str(item.code) in {"PP3", "BP4"}:
            _attach_metadata(item, metadata, applied=True, notes=[note])
            item.review_flags = _append_flag(item.review_flags, "VCEP_COMPUTATIONAL_REVIEW_REQUIRED", note)
    return items


def override_provenance(context: VCEPOverrideContext | None) -> dict[str, Any] | None:
    if context is None:
        return None
    return {
        "override_enabled": context.override_enabled,
        "override_applied": context.applied,
        "active_profile": profile_summary(context.active_profile) if context.active_profile else None,
        "blocked_reasons": list(context.blocked_reasons),
        "provenance": context.provenance,
    }


def _stricter_computational_value(key: str, current: Any, override: Any) -> Any:
    try:
        current_number = float(current)
        override_number = float(override)
    except (TypeError, ValueError):
        return current
    if key.startswith("min_"):
        return max(current_number, override_number)
    if key.endswith("_pathogenic"):
        return max(current_number, override_number)
    if key.endswith("_benign"):
        return min(current_number, override_number)
    return current


def _downgrade_needed(current: str, maximum: str) -> bool:
    return PVS1_STRENGTH_ORDER.get(current, 0) > PVS1_STRENGTH_ORDER.get(maximum, 0)


def _make_candidate_only(item: EvidenceItem, reason: str, metadata: dict[str, Any]) -> None:
    item.applied = False
    item.candidate_only = True
    item.strength = EvidenceStrength.NONE
    if not item.reason.startswith("Candidate-only"):
        item.reason = f"Candidate-only after VCEP profile override: {item.reason}"
    item.supporting_data["applied"] = False
    item.supporting_data["candidate_only"] = True
    item.supporting_data["evidence_status"] = "candidate"
    _attach_metadata(item, metadata, applied=False, notes=[reason])
    item.review_flags = _append_flag(item.review_flags, "VCEP_CRITERION_DISABLED_OR_CANDIDATE_ONLY", reason)


def _attach_metadata(
    item: EvidenceItem,
    metadata: dict[str, Any],
    *,
    applied: bool,
    notes: list[str],
) -> None:
    item.supporting_data["vcep_override"] = {
        **metadata,
        "override_applied_to_item": applied,
        "notes": _unique(notes),
    }


def _append_flag(flags: list[ReviewFlag], code: str, message: str) -> list[ReviewFlag]:
    output = list(flags)
    if not any(flag.code == code for flag in output):
        output.append(ReviewFlag(code=code, message=message, severity="warning", blocking=False))
    return output


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
