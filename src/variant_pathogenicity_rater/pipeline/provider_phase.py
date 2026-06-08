from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from variant_pathogenicity_rater.providers import build_variant_identity
from variant_pathogenicity_rater.schemas.variant import Variant


@dataclass(frozen=True)
class ProviderPhaseResult:
    provider_identity: Any


def run_provider_phase(
    *,
    options: dict[str, Any],
    original_normalized_variant: Variant,
    variant_resolution: Any = None,
    step_results: dict[str, Any],
) -> ProviderPhaseResult:
    provider_identity = build_variant_identity(
        normalized_variant=original_normalized_variant,
        variant_resolution=variant_resolution,
        explicit_aliases=options.get("provider_identity_aliases"),
    )
    step_results["provider_identity"] = provider_identity.model_dump(mode="json")
    return ProviderPhaseResult(provider_identity=provider_identity)
