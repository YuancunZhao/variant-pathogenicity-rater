# Provider Architecture

79A-1 adds a provider-layer `VariantIdentity` contract. This is an additive
identity and alias surface for providers only. It does not generate ACMG
evidence, does not call online providers, does not change evidence generation,
and does not modify the ACMG combiner.

## Provider-Layer VariantIdentity

The provider-layer model lives in:

- `src/variant_pathogenicity_rater/providers/identity.py`
- `src/variant_pathogenicity_rater/providers/identity_adapter.py`

It is separate from the existing normalization identity model in
`schemas.variant.VariantIdentity`.

The provider-layer identity captures:

- gene, transcript, HGVS c., HGVS p., HGVS g.;
- genome build, chromosome, position, ref, and alt;
- provider aliases such as gnomAD variant ID, ClinVar Variation ID, rsID, and
  ClinGen Allele Registry CA ID;
- descriptive protein change and consequence;
- identity confidence, conflicts, provenance, limitations, and review flags.

This identity is not ACMG evidence. It is emitted for provider-readiness audit
and future provider orchestration only.

## Adapters

79A-1 includes read-only adapters that derive provider identity from existing
pipeline outputs:

- `variant_identity_from_normalized_variant(...)`
- `variant_identity_from_resolution(...)`
- `merge_variant_identities(...)`
- `build_variant_identity(...)`

The merge policy preserves base identity fields, fills missing fields from
updates, and records gene/transcript/HGVS/coordinate/ref/alt/build conflicts as
identity conflicts and review flags. Conflicts are not silently overwritten.

## gnomAD Identity Validation

`build_gnomad_variant_id(...)` and `validate_gnomad_variant_id(...)` construct a
gnomAD-style `chrom-pos-ref-alt` ID only when the provider-layer identity has a
supported genome build, chromosome, position, ref, and alt with basic allele
grammar.

Invalid or incomplete gnomAD identity becomes an identity limitation. It is not
a gnomAD provider failure and it is not evidence of population absence. Later
79A provider orchestration should skip gnomAD before querying when this
validated ID is unavailable.

## Provider Aliases

Provider alias helpers are offline and deterministic:

- `identity_aliases_for_clinvar(...)`
- `identity_aliases_for_vep(...)`
- `identity_aliases_for_literature(...)`

They expose existing gene, transcript HGVS, protein, coordinate, rsID, ClinVar
Variation ID, and CA ID aliases without querying external databases.

## Current Integration

`rate_variant` now emits additive `provider_identity` output and mirrors it in
the canonical `variant.provider_identity` section. Existing fields remain
present, including `normalized_variant`, `resolved_variant`,
`variant_resolution`, `normalization_identity`, provider runtime summaries, and
evidence outputs.

79A-1 does not replace existing provider calls. 79A-2 and 79A-3 are the planned
follow-ups for resolution orchestration and provider dependency orchestration.
