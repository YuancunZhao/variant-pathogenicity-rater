"""Provider-layer contracts and adapters.

These models describe provider input identity and aliases only. They do not
create ACMG evidence and are not provider orchestrators.
"""

from variant_pathogenicity_rater.providers.identity import (
    VariantIdentity,
    build_gnomad_variant_id,
    identity_aliases_for_clinvar,
    identity_aliases_for_literature,
    identity_aliases_for_vep,
    validate_gnomad_variant_id,
)
from variant_pathogenicity_rater.providers.identity_adapter import (
    build_variant_identity,
    merge_variant_identities,
    variant_identity_from_normalized_variant,
    variant_identity_from_resolution,
)

__all__ = [
    "VariantIdentity",
    "build_gnomad_variant_id",
    "validate_gnomad_variant_id",
    "identity_aliases_for_clinvar",
    "identity_aliases_for_vep",
    "identity_aliases_for_literature",
    "variant_identity_from_normalized_variant",
    "variant_identity_from_resolution",
    "merge_variant_identities",
    "build_variant_identity",
]
