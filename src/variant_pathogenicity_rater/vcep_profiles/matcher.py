from __future__ import annotations

from datetime import datetime, timezone

from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.vcep_profiles.schema import (
    VCEPOverrideContext,
    VCEPProfile,
    VCEPProfileMatch,
    VCEPProfileStatus,
    VCEPSignalResult,
    profile_summary,
)


MISSING_DISEASE = {"", "unknown", "not provided", "unspecified", "not specified"}


def resolve_vcep_signal_and_overrides(
    *,
    profiles: list[VCEPProfile],
    variant: Variant,
    context: GeneDiseaseContext,
    include_signals: bool,
    apply_overrides: bool,
) -> tuple[VCEPSignalResult | None, VCEPOverrideContext | None]:
    if not include_signals and not apply_overrides:
        return None, None

    matches = [_match_profile(profile, variant, context) for profile in profiles]
    matches = [match for match in matches if match.match_level != "none"]
    warnings: list[str] = []
    limitations: list[str] = []
    review_flags: list[ReviewFlag] = []

    for match in matches:
        profile = match.profile
        warnings.append(
            f"VCEP/gene-specific guidance may exist for {profile.gene} / {profile.disease} "
            f"({profile.vcep_name}, {profile.status}). Signal only unless approved overrides are explicitly enabled."
        )
        review_flags.extend(match.review_flags)
        if profile.status == VCEPProfileStatus.DEPRECATED:
            limitations.append(f"Deprecated VCEP profile detected and not applied: {profile.profile_id}.")
        if profile.status in {VCEPProfileStatus.DRAFT, VCEPProfileStatus.PROVISIONAL}:
            limitations.append(
                f"{profile.status.title()} VCEP profile detected as signal only: {profile.profile_id}."
            )

    signal = VCEPSignalResult(
        profiles_checked=len(profiles),
        matches=matches,
        warnings=_unique(warnings),
        limitations=_unique(limitations),
        review_flags=_unique_flags(review_flags),
        provenance=[
            {
                "component": "vcep_signal_override_framework",
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                "profile_count": len(profiles),
                "match_count": len(matches),
                "scope": "signals and limited generator parameter overrides only; not ACMG evidence",
            }
        ],
    )

    override_context = _build_override_context(matches, apply_overrides)
    return signal, override_context


def _match_profile(
    profile: VCEPProfile,
    variant: Variant,
    context: GeneDiseaseContext,
) -> VCEPProfileMatch:
    matched: list[str] = []
    mismatches: list[str] = []
    blockers: list[str] = []
    flags: list[ReviewFlag] = []

    if _norm(profile.gene) != _norm(variant.gene_symbol or context.gene_symbol):
        return VCEPProfileMatch(profile=profile, match_level="none")
    matched.append("gene")

    disease = context.disease_name or ""
    if _missing_disease(disease):
        mismatches.append("Disease context is missing; profile applicability cannot be confirmed.")
        blockers.append("Missing disease context blocks VCEP override application.")
        flags.append(
            _flag(
                "VCEP_PROFILE_MISSING_DISEASE",
                "Disease context is missing for VCEP profile matching.",
                True,
            )
        )
    elif _disease_matches(profile.disease, disease):
        matched.append("disease")
    else:
        return VCEPProfileMatch(profile=profile, match_level="none")

    if profile.inheritance:
        if not context.inheritance_mode:
            mismatches.append("Inheritance context is missing; profile applicability cannot be confirmed.")
            blockers.append("Missing inheritance context blocks VCEP override application.")
            flags.append(
                _flag(
                    "VCEP_PROFILE_MISSING_INHERITANCE",
                    "Inheritance context is missing for VCEP profile matching.",
                    True,
                )
            )
        elif _norm(profile.inheritance) == _norm(context.inheritance_mode):
            matched.append("inheritance")
        else:
            mismatches.append("Inheritance context does not match the VCEP profile.")
            blockers.append("Inheritance mismatch blocks VCEP override application.")
            flags.append(
                _flag(
                    "VCEP_PROFILE_INHERITANCE_MISMATCH",
                    "Inheritance differs from the matched VCEP profile.",
                    True,
                )
            )

    transcript = _transcript_label(variant) or _transcript_label(context)
    if profile.applicable_transcripts:
        allowed = {_norm_transcript(item) for item in profile.applicable_transcripts}
        if not transcript:
            blockers.append("Missing transcript context blocks transcript-scoped VCEP override application.")
            flags.append(
                _flag(
                    "VCEP_PROFILE_TRANSCRIPT_MISSING",
                    "Transcript context is missing for a transcript-scoped VCEP profile.",
                    True,
                )
            )
        elif _norm_transcript(transcript) not in allowed:
            mismatches.append("Transcript context does not match applicable_transcripts.")
            blockers.append("Transcript mismatch blocks VCEP override application.")
            flags.append(
                _flag(
                    "VCEP_PROFILE_TRANSCRIPT_MISMATCH",
                    "Transcript differs from the matched VCEP profile.",
                    True,
                )
            )
        else:
            matched.append("transcript")

    if "disease" in matched and not blockers:
        level = "gene_disease"
        confidence = 0.8
    elif "gene" in matched:
        level = "gene_signal"
        confidence = 0.45
    else:
        level = "none"
        confidence = 0.0

    flags.append(
        _flag(
            "VCEP_PROFILE_MATCH",
            "VCEP/gene-specific guidance may exist; review profile applicability.",
            False,
        )
    )
    return VCEPProfileMatch(
        profile=profile,
        match_level=level,
        matched_fields=matched,
        mismatch_reasons=mismatches,
        override_blocking_reasons=blockers,
        review_flags=_unique_flags(flags),
        confidence=confidence,
    )


def _build_override_context(
    matches: list[VCEPProfileMatch],
    apply_overrides: bool,
) -> VCEPOverrideContext:
    if not matches:
        return VCEPOverrideContext(
            override_enabled=apply_overrides,
            applied=False,
            blocked_reasons=[],
            provenance={"matched_profiles": [], "override_applied": False},
        )

    approved = [
        match
        for match in matches
        if match.profile.status == VCEPProfileStatus.APPROVED
        and match.match_level == "gene_disease"
        and not match.override_blocking_reasons
    ]
    blocked: list[str] = []
    flags: list[ReviewFlag] = []

    if not apply_overrides:
        blocked.append("VCEP overrides were not explicitly enabled.")
    if len(approved) > 1:
        blocked.append("Multiple approved VCEP profiles matched; overrides were blocked pending review.")
        flags.append(
            _flag(
                "VCEP_PROFILE_CONFLICT",
                "Multiple approved VCEP profiles matched; no override was applied.",
                True,
            )
        )
    for match in matches:
        if match.profile.status != VCEPProfileStatus.APPROVED:
            blocked.append(f"Profile {match.profile.profile_id} is {match.profile.status}; signal only.")
        blocked.extend(match.override_blocking_reasons)
        flags.extend(match.review_flags)

    if apply_overrides and len(approved) == 1:
        profile = approved[0].profile
        return VCEPOverrideContext(
            override_enabled=True,
            applied=True,
            active_profile=profile,
            source_profile_id=profile.profile_id,
            source_version=profile.version,
            population_threshold_overrides=dict(profile.population_threshold_overrides),
            pvs1_overrides=dict(profile.pvs1_overrides),
            computational_overrides=dict(profile.computational_overrides),
            ps1_pm5_overrides=dict(profile.ps1_pm5_overrides),
            disabled_criteria=list(profile.disabled_criteria),
            review_required_flags=[
                _flag(
                    str(raw.get("code") or "VCEP_PROFILE_REVIEW_REQUIRED"),
                    str(raw.get("message") or "VCEP profile override requires human review."),
                    bool(raw.get("blocking", False)),
                )
                for raw in profile.review_required_flags
            ],
            blocked_reasons=[],
            provenance={"active_profile": profile_summary(profile)},
        )

    return VCEPOverrideContext(
        override_enabled=apply_overrides,
        applied=False,
        blocked_reasons=_unique(blocked),
        review_required_flags=_unique_flags(flags),
        provenance={
            "matched_profiles": [profile_summary(match.profile) for match in matches],
            "override_applied": False,
        },
    )


def _flag(code: str, message: str, blocking: bool) -> ReviewFlag:
    return ReviewFlag(
        code=code,
        message=message,
        severity="error" if blocking else "warning",
        blocking=blocking,
    )


def _disease_matches(profile_disease: str, context_disease: str) -> bool:
    profile = _norm(profile_disease)
    context = _norm(context_disease)
    return bool(profile and context and (profile == context or profile in context or context in profile))


def _missing_disease(value: str) -> bool:
    return _norm(value) in MISSING_DISEASE


def _norm(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _norm_transcript(value: str | None) -> str:
    return str(value or "").strip().split(":", 1)[0].lower()


def _transcript_label(obj: object) -> str | None:
    transcript = getattr(obj, "transcript", None)
    if transcript is None:
        return None
    accession = getattr(transcript, "accession", None)
    if not accession:
        return None
    version = getattr(transcript, "version", None)
    return f"{accession}.{version}" if version else str(accession)


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
