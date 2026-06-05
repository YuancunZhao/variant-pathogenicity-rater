from __future__ import annotations

from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel
from variant_pathogenicity_rater.variant_resolution.schema import ResolutionOutcome


class ResolutionProviderResult(SchemaModel):
    provider: str
    outcome: ResolutionOutcome
    source_version: str | None = None
    cache_hit: bool | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    result: dict[str, Any] | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
