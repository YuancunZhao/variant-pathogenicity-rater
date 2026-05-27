from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


class VCEPProfileStatus(StrEnum):
    APPROVED = "approved"
    PROVISIONAL = "provisional"
    DRAFT = "draft"
    DEPRECATED = "deprecated"


class VCEPProfile(SchemaModel):
    profile_id: str = Field(..., min_length=1)
    gene: str = Field(..., min_length=1)
    disease: str = Field(..., min_length=1)
    inheritance: str | None = None
    vcep_name: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    status: VCEPProfileStatus
    effective_date: date | None = None
    citations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    applicable_transcripts: list[str] = Field(default_factory=list)
    rule_signals: list[dict[str, Any]] = Field(default_factory=list)
    population_threshold_overrides: dict[str, Any] = Field(default_factory=dict)
    pvs1_overrides: dict[str, Any] = Field(default_factory=dict)
    computational_overrides: dict[str, Any] = Field(default_factory=dict)
    ps1_pm5_overrides: dict[str, Any] = Field(default_factory=dict)
    disabled_criteria: list[str] = Field(default_factory=list)
    review_required_flags: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class VCEPProfileMatch(SchemaModel):
    profile: VCEPProfile
    match_level: str = "none"
    matched_fields: list[str] = Field(default_factory=list)
    mismatch_reasons: list[str] = Field(default_factory=list)
    override_blocking_reasons: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)


class VCEPSignalResult(SchemaModel):
    profiles_checked: int = 0
    matches: list[VCEPProfileMatch] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class VCEPOverrideContext(SchemaModel):
    override_enabled: bool = False
    applied: bool = False
    active_profile: VCEPProfile | None = None
    source_profile_id: str | None = None
    source_version: str | None = None
    population_threshold_overrides: dict[str, Any] = Field(default_factory=dict)
    pvs1_overrides: dict[str, Any] = Field(default_factory=dict)
    computational_overrides: dict[str, Any] = Field(default_factory=dict)
    ps1_pm5_overrides: dict[str, Any] = Field(default_factory=dict)
    disabled_criteria: list[str] = Field(default_factory=list)
    review_required_flags: list[ReviewFlag] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


def profile_summary(profile: VCEPProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "gene": profile.gene,
        "disease": profile.disease,
        "inheritance": profile.inheritance,
        "vcep_name": profile.vcep_name,
        "source": profile.source,
        "version": profile.version,
        "status": profile.status,
        "effective_date": profile.effective_date.isoformat() if profile.effective_date else None,
        "citations": list(profile.citations),
    }
