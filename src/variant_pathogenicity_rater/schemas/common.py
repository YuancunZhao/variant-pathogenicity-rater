from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SchemaModel(BaseModel):
    """Shared model behavior for JSON-serializable MCP payloads."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
        use_enum_values=True,
    )


class AuditTrail(SchemaModel):
    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str = Field(default="system", min_length=1)
    tool_name: str | None = None
    query: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    checksum: str | None = None
    notes: list[str] = Field(default_factory=list)


class ReviewFlag(SchemaModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    severity: str = Field(default="warning", pattern="^(info|warning|error)$")
    blocking: bool = False
    audit_trail: list[AuditTrail] = Field(default_factory=list)
