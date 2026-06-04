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

`provider_mode_summary` remains the backward-compatible top-level provider
summary. Existing keys remain present:

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

`providers.summary` remains equal to `provider_mode_summary` for compatibility.
Per-provider canonical entries prefer `step_results.provider_runtime` when
available.

## Safety Semantics

Provider outcomes are audit state, not ACMG evidence.

- `no_record` is not evidence of population absence and does not trigger PM2.
- `failure`, `partial`, and `unavailable` become limitations or review context.
- ClinVar, ClinGen ERepo, and literature records remain review-note or
  candidate-only unless explicitly promoted through reviewed evidence.
- Online providers remain disabled by default.
- Raw provider `step_results` payloads remain available for audit/debugging.
