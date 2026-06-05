# Runtime Options

77D adds a centralized RuntimeOptions normalization layer for Python API, CLI,
MCP, natural-language text, batch, and annotated-batch option handling.

This is an additive compatibility layer. It does not change variant
normalization, provider retrieval semantics, evidence generation, reviewed
evidence validation, the ACMG combiner, final classification, report rendering,
or default offline behavior.

## Scope

77D-1 introduced the foundation and wired the `rate_variant` core `_options()`
path. 77D-2 migrates CLI, MCP, natural-language text, batch, and annotated-batch
entry points onto the same RuntimeOptions interpretation layer.

All public CLI arguments, MCP schemas, Python API fields, and legacy option keys
remain available. RuntimeOptions returns legacy-compatible dictionaries to the
existing pipeline so the migration remains an adapter/refactor layer.

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
- `runtime_options_from_cli(args, command)`
- `runtime_options_from_mcp(arguments, tool_name)`
- `runtime_options_from_text_input(parsed_input, explicit_options, language, output, report_mode)`
- `runtime_options_for_batch(batch_options, record, input_index)`
- `runtime_options_to_pipeline_dict(runtime_options)`
- `runtime_options_snapshot(runtime_options)`
- `apply_online_provider_modes(runtime_options)`

`runtime_options_to_pipeline_dict()` returns a legacy-compatible dictionary so
existing pipeline code can continue consuming `options` without broad rewrites.
`runtime_options_snapshot()` supplies the descriptive
`runtime.runtime_options_snapshot` canonical output view.

## Entry Point Migration

- CLI `rate`, `rate-text`, `batch`, and `annotated-batch` build RuntimeOptions
  before calling pipeline functions.
- MCP `rate_variant`, `rate_variant_from_text`, `parse_variant_text`,
  `rate_variant_batch`, and `rate_annotated_variants` normalize options in the
  handler without changing input schemas.
- `rate_variant_from_text()` uses `runtime_options_from_text_input()` to merge
  parsed options, explicit language/report arguments, and explicit options with
  deterministic precedence.
- Batch records use `runtime_options_for_batch()` so record-level overrides stay
  isolated from batch-level defaults.
- Annotated-batch records normalize annotation-derived options before they enter
  the batch pipeline.

Text input precedence is:

1. explicit options;
2. explicit language/report arguments;
3. parsed-input options;
4. defaults.

Batch precedence is:

1. record-level options;
2. batch-level options;
3. defaults.

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
  `reviewed_evidence` as the preferred runtime value. Entry-point adapters avoid
  duplicating top-level reviewed evidence into `options` when the pipeline must
  retain legacy top-level precedence behavior.
- `mock_supplemental_evidence_items` remains compatible and keeps the existing
  precedence over `supplemental_evidence_items`.
- Provider cache directory configuration alone does not enable online access.
- Missing or unknown options are not evidence and do not change
  classification.
