# Provider Architecture

79A-1 adds a provider-layer `VariantIdentity` contract, and 79A-2 adds
provider dependency gating for the current online provider paths. These are
additive provider-readiness surfaces only. They do not generate ACMG evidence,
do not change evidence generation, and do not modify the ACMG combiner.

81A-3 decomposed the single-variant pipeline into phase modules. Provider
architecture now sits inside this phase flow:

```text
rate_variant
  -> normalization_phase
  -> resolution_phase
  -> provider_phase
  -> evidence_phase
  -> classification_phase
  -> output_phase
```

`provider_phase` prepares provider identity. `evidence_phase` executes provider
queries, applies dependency gating for current provider paths, and passes
provider-derived facts into the existing evidence-generation and review-note
boundaries. `classification_phase` and `output_phase` consume the resulting
state; they do not run provider queries.

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
a gnomAD provider failure and it is not evidence of population absence.

79A-2 gates the current online gnomAD path before GraphQL. When a validated
`gnomad_variant_id` is unavailable, the population provider runtime outcome is
`skipped` with `attempted=false` and a `dependency_status` payload. This is
distinct from `no_record`, which is reserved for a valid provider query that
successfully executes and returns no matching variant.

## Provider Aliases

Provider alias helpers are offline and deterministic:

- `identity_aliases_for_clinvar(...)`
- `identity_aliases_for_vep(...)`
- `identity_aliases_for_literature(...)`

They expose existing gene, transcript HGVS, protein, coordinate, rsID, ClinVar
Variation ID, and CA ID aliases without querying external databases.

## Dependency Gating

The provider dependency contract lives in
`src/variant_pathogenicity_rater/providers/dependencies.py`.

It defines:

- `ProviderDependency`
- `ProviderDependencyCheck`
- `ProviderDependencyStatus`

Current checks:

- gnomAD requires a validated provider-layer `gnomad_variant_id`.
- VEP requires either usable coordinate identity or HGVS fallback identity.
- ClinVar requires at least one query alias such as Variation ID, rsID, HGVS,
  gene+HGVS, or coordinate.
- Literature requires a gene, variant alias, search query, or PMID.

The 79A-2 pipeline integration is intentionally light. It gates current online
provider paths before the provider is constructed, writes dependency skip
payloads into `step_results`, and lets the existing `ProviderRuntimeResult`
surface report `outcome=skipped`. It does not replace existing providers or add
a full orchestrator.

## Current Integration

`rate_variant` now orchestrates phase modules. It emits additive
`provider_identity` output through `provider_phase` and mirrors it in the
canonical `variant.provider_identity` section. Existing fields remain present,
including `normalized_variant`, `resolved_variant`, `variant_resolution`,
`normalization_identity`, provider runtime summaries, and evidence outputs.

`VariantIdentity`, `ProviderDependency`, and `ProviderRuntimeResult` are
phase-level contracts:

- `VariantIdentity` is prepared in `provider_phase` from normalized and
  resolved variant state.
- `ProviderDependency` checks are applied in `evidence_phase` before online
  provider calls that require usable identity.
- `ProviderRuntimeResult` is constructed in `output_phase` from provider step
  payloads and dependency skip payloads, then serialized into
  `step_results.provider_runtime`, `provider_mode_summary` (a legacy
  compatibility view projected from `ProviderRuntimeResult`), and canonical
  provider sections. `build_provider_runtime_results` is the only function
  that interprets raw provider step payloads.

79A-2 does not replace existing provider calls. The planned follow-up is a
fuller provider orchestrator that can route resolution, annotation, population,
clinical assertion, and literature providers through the same dependency
contract.
