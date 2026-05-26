from __future__ import annotations

from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel


class PopulationQualityCheck(SchemaModel):
    name: str = Field(..., min_length=1)
    passed: bool
    observed: Any | None = None
    expected: Any | None = None
    reason: str = Field(..., min_length=1)
    blocking: bool = True


class PopulationEvidenceDecision(SchemaModel):
    recommended_code: str | None = None
    strength: str = "none"
    direction: str = "neutral"
    applied: bool = False
    candidate_only: bool = False
    decision_path: list[str] = Field(default_factory=list)
    thresholds_used: dict[str, Any] = Field(default_factory=dict)
    quality_checks: list[PopulationQualityCheck] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    downgrade_reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

