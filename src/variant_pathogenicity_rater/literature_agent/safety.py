from __future__ import annotations

from typing import Any


NOT_APPLIED_REASON = (
    "Not automatically applied to ACMG classification; qualified human review is required."
)


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "confirmed", "adequate", "valid"}
    return bool(value)


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def candidate(code: str) -> str:
    return code if code.endswith("_candidate") else f"{code}_candidate"


def base_limitations() -> list[str]:
    return [
        "Literature agent output is suggested evidence only.",
        "Suggested evidence is not added to applied evidence.",
        "The ACMG classification combiner is not invoked or modified.",
        "Manual review is required before any ACMG criterion can be applied.",
    ]


def confidence(record: dict[str, Any], default: float = 0.55) -> float:
    value = record.get("confidence", record.get("extraction_confidence", default))
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
