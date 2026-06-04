# Runtime Options

77D-1 adds a centralized RuntimeOptions normalization foundation for the
Python API and core `rate_variant` option path.

This is an additive compatibility layer. It does not change variant
normalization, provider retrieval semantics, evidence generation, reviewed
evidence validation, the ACMG combiner, final classification, report rendering,
or default offline behavior.

## Scope

77D-1 wires only the `rate_variant` core `_options()` path through the shared
normalizer. CLI, MCP, batch, annotated-batch, and natural-language wrappers keep
their existing argument surfaces and wrapper-specific option assembly for now.
Later 77D tasks can migrate those wrappers onto the same helper without
renaming or deleting public fields.

## RuntimeOptions Fields

`src/variant_pathogenicity_rater/runtime/options.py` defines `RuntimeOptions`
with these normalized fields:

- `use_online_clinvar`
- `use_online_gnomad`
- `use_online_vep`
- `use_online_pubmed`
- `use_online_litvar`
- `provider_cache_dir`
- `provider_timeout`
- `provider_email`
- `provider_user_agent`
- `report_language`
- `report_mode`
- `disease`
- `inheritance`
- `confirmed_context`
- `reviewed_evidence`
- `supplemental_evidence_items`
- `mock_mode`
- `option_sources`
- `normalization_warnings`
- `passthrough_options`

Unknown legacy options are preserved in `passthrough_options` and are emitted
back into the legacy pipeline option dictionary. This preserves VCEP profile
paths, thresholds, fixtures, local provider files, `include_*` flags,
literature records, transcript fixtures, `data_sources` overrides, and other
existing extension fields.

## Helpers

The module exposes:

- `normalize_runtime_options(options=None, top_level=None, source="python_api")`
- `merge_runtime_options(base, override, source)`
- `runtime_options_to_pipeline_dict(runtime_options)`
- `apply_online_provider_modes(runtime_options)`

`runtime_options_to_pipeline_dict()` returns a legacy-compatible dictionary so
existing pipeline code can continue consuming `options` without broad rewrites.

## Online Provider Mapping

Online providers remain disabled by default. The online flags default to
`false`, and `mock_mode` defaults to `true`.

When an explicit online flag is supplied, RuntimeOptions generates the same
`data_sources.sources` overrides that the previous `rate_variant` helper
generated:

- `use_online_clinvar` -> `clinvar`, live label
  `NCBI ClinVar E-utilities live`, cache subdir `clinvar`
- `use_online_gnomad` -> `population`, live label
  `gnomAD gnomad_r4 live GraphQL`, cache subdir `gnomad`
- `use_online_vep` -> `computational`, live label
  `Ensembl REST VEP live`, cache subdir `vep`
- `use_online_pubmed` or `use_online_litvar` -> `literature`, live label
  `PubMed/LitVar live`, cache subdir `literature`

Existing `data_sources` overrides are preserved. Explicit source versions and
cache directories are not overwritten.

## Compatibility Rules

- Top-level reviewed evidence precedence remains handled by the existing
  pipeline reviewed-evidence workflow.
- `normalize_runtime_options(..., top_level=...)` records top-level
  `reviewed_evidence` as the preferred runtime value for future wrappers, but
  77D-1 does not force that value into the core pipeline path.
- `mock_supplemental_evidence_items` remains compatible and keeps the existing
  precedence over `supplemental_evidence_items`.
- Provider cache directory configuration alone does not enable online access.
- Missing or unknown options are not evidence and do not change
  classification.
