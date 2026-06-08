# Provider Result Contract

77B adds an additive provider runtime contract for provider outcome and
provenance reporting.

The contract normalizes provider state only. It does not change provider
retrieval, evidence generation, the ACMG combiner, final classification, or
default offline behavior.

## Runtime Result

`ProviderRuntimeResult` is emitted under `step_results.provider_runtime` for:

- ClinVar
- population / gnomAD
- computational / VEP
- literature / PubMed-LitVar
- ClinGen ERepo

Fields:

- `provider_name`
- `requested_mode`
- `configured_mode`
- `attempted`
- `outcome`
- `records_count`
- `source_version`
- `query`
- `endpoint`
- `cache_hit`
- `limitations`
- `warnings`
- `error_type`
- `error_message_summary`
- `raw_record_hash`
- `retrieval_timestamp`
- `provenance`

Valid outcomes:

- `success`
- `no_record`
- `failure`
- `skipped`
- `cache_hit`
- `partial`
- `unavailable`

## Compatibility Summary

`provider_mode_summary` is a **legacy compatibility view** projected from
`ProviderRuntimeResult`. It remains emitted unchanged for backward
compatibility but is no longer the authoritative provider summary. New
clients should prefer `providers.summary` and the per-provider canonical
entries under `step_results.provider_runtime`.

Legacy keys remain present in `provider_mode_summary`:

- `requested_mode`
- `configured_mode`
- `actual_outcome`
- `source_version`
- `endpoint`
- `query`
- `raw_hash`
- `cache_hit`
- `provider_mode`
- `records_count`
- `limitations_count`
- `limitations`

77B adds these non-breaking keys:

- `attempted`
- `outcome`
- `warnings`
- `error_type`
- `error_message_summary`
- `raw_record_hash`
- `retrieval_timestamp`
- `provenance`

`providers.summary` is projected from `step_results.provider_runtime` (the
ground-truth provider runtime contract). For freshly generated outputs,
`providers.summary` equals `provider_mode_summary`. Per-provider canonical
entries prefer `step_results.provider_runtime` when available.

## Yield Observations

81B adds a non-semantic `yield_observations` dictionary to
`ProviderRuntimeResult`. This field carries provider-specific metadata that
benchmark and reporting consumers need for yield metrics (candidate evidence
counts, literature per-source article/citation counts, population data-source
labels) without reading raw provider step payloads.

`yield_observations` is populated by `provider_result_from_step_payload` — the
only function that interprets raw step payload shapes. All consumers
(``providers.summary`` projection, benchmark yield metrics, data-source
version extraction) read from ``ProviderRuntimeResult``, not from raw step
payloads.

## Safety Semantics

Provider outcomes are audit state, not ACMG evidence.

- `no_record` is not evidence of population absence and does not trigger PM2.
- `failure`, `partial`, and `unavailable` become limitations or review context.
- ClinVar, ClinGen ERepo, and literature records remain review-note or
  candidate-only unless explicitly promoted through reviewed evidence.
- Online providers remain disabled by default.
- Raw provider `step_results` payloads remain available for audit/debugging.
