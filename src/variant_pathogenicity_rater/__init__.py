"""Variant Pathogenicity Rater package."""

from variant_pathogenicity_rater.natural_language_input import (
    parse_variant_text,
    rate_variant_from_text,
)
from variant_pathogenicity_rater.variant_resolution import resolve_variant


__all__ = ["parse_variant_text", "rate_variant_from_text", "resolve_variant"]
