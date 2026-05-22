"""Variant normalization services."""

from variant_pathogenicity_rater.normalization.normalizer import (
    NormalizationError,
    build_variant_identity,
    normalize_variant,
)

__all__ = ["NormalizationError", "build_variant_identity", "normalize_variant"]
