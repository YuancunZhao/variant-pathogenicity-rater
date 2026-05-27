from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.vcep_profiles.schema import (
    VCEPOverrideContext,
    VCEPSignalResult,
    profile_summary,
)


def vcep_report_payload(
    signal: VCEPSignalResult | None,
    override_context: VCEPOverrideContext | None,
) -> dict[str, Any] | None:
    if signal is None and override_context is None:
        return None
    return {
        "note": (
            "VCEP profile signals and rule overrides are review context. "
            "Signals alone are not ACMG evidence and were not counted by the combiner."
        ),
        "profiles_checked": signal.profiles_checked if signal else 0,
        "matches": [
            {
                "profile": profile_summary(match.profile),
                "match_level": match.match_level,
                "matched_fields": list(match.matched_fields),
                "mismatch_reasons": list(match.mismatch_reasons),
                "override_blocking_reasons": list(match.override_blocking_reasons),
                "confidence": match.confidence,
            }
            for match in (signal.matches if signal else [])
        ],
        "warnings": list(signal.warnings if signal else []),
        "limitations": list(signal.limitations if signal else []),
        "override_context": (
            {
                "override_enabled": override_context.override_enabled,
                "override_applied": override_context.applied,
                "active_profile": (
                    profile_summary(override_context.active_profile)
                    if override_context.active_profile
                    else None
                ),
                "blocked_reasons": list(override_context.blocked_reasons),
                "population_threshold_overrides": dict(override_context.population_threshold_overrides),
                "pvs1_overrides": dict(override_context.pvs1_overrides),
                "computational_overrides": dict(override_context.computational_overrides),
                "ps1_pm5_overrides": dict(override_context.ps1_pm5_overrides),
                "disabled_criteria": list(override_context.disabled_criteria),
            }
            if override_context
            else None
        ),
        "provenance": list(signal.provenance if signal else []),
    }
