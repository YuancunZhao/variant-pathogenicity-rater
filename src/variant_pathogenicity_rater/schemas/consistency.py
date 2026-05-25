from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel


ConsistencyStatus = Literal["ok", "warning", "conflict", "insufficient"]
ConsistencySeverity = Literal["ok", "warning", "conflict", "insufficient"]


class ContextConsistencyCheck(SchemaModel):
    check_name: str = Field(..., min_length=1)
    severity: ConsistencySeverity
    field: str = Field(..., min_length=1)
    expected: Any | None = None
    observed: Any | None = None
    reason: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    requires_review: bool = True


class ContextConsistency(SchemaModel):
    status: ConsistencyStatus
    checks: list[ContextConsistencyCheck] = Field(default_factory=list)
    conflicts: list[ContextConsistencyCheck] = Field(default_factory=list)
    warnings: list[ContextConsistencyCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_required: bool = True
    provenance: list[dict[str, Any]] = Field(default_factory=list)
