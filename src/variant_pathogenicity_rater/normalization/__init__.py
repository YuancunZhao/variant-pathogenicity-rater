"""Variant normalization services."""

from variant_pathogenicity_rater.normalization.normalizer import (
    NormalizationError,
    normalize_variant,
)

__all__ = ["NormalizationError", "normalize_variant"]
