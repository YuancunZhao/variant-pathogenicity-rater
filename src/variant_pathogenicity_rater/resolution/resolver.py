from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.variant_resolution import resolve_variant as _resolve_variant
from variant_pathogenicity_rater.variant_resolution.schema import VariantResolutionResult


def resolve_variant(
    variant: dict[str, Any] | Any,
    *,
    context: Any | None = None,
    options: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> VariantResolutionResult:
    return _resolve_variant(variant, context=context, options=options, records=records)
