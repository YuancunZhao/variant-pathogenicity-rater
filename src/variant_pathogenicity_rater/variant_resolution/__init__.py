from variant_pathogenicity_rater.variant_resolution.resolution_pipeline import resolve_variant
from variant_pathogenicity_rater.variant_resolution.schema import (
    ExonContext,
    NMDContext,
    ResolvedCoordinate,
    ResolvedProtein,
    ResolvedTranscript,
    ResolutionOutcome,
    VariantResolutionRecord,
    VariantResolutionResult,
)

__all__ = [
    "ExonContext",
    "NMDContext",
    "ResolvedCoordinate",
    "ResolvedProtein",
    "ResolvedTranscript",
    "ResolutionOutcome",
    "VariantResolutionRecord",
    "VariantResolutionResult",
    "resolve_variant",
]
