"""End-to-end SNV/small indel ACMG workflow orchestration."""

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant

__all__ = ["rate_variant"]
