# Online Provider Safety

Online provider support is an opt-in retrieval layer. It does not change the
ACMG combiner, does not relax evidence safety rules, and does not authorize
autonomous clinical interpretation.

The 74 real provider pipeline is implemented and has passed offline integration
review with `655 passed, 2 skipped`. Live provider smoke validation is
implemented, env-gated by `VPR_RUN_LIVE_PROVIDER_SMOKE=1`, and skipped by
default. See `docs/LIVE_PROVIDER_SMOKE_VALIDATION.md`.

## Default-Off Rules

- Online ClinVar, gnomAD, Ensembl VEP, PubMed, and LitVar are disabled by
  default.
- Default pytest must not require network access.
- Optional live smoke tests require `VPR_RUN_LIVE_PROVIDER_SMOKE=1` and are
  skipped by default. LitVar additionally requires
  `VPR_RUN_LIVE_LITVAR_SMOKE=1` because that endpoint is treated as
  optional/experimental.
- CLI and MCP online flags set `online_enabled=true` only for the requested
  provider.
- Provider cache directories are explicit configuration, not a signal to enable
  online retrieval by themselves.
- `mock_mode` is retained as a backward-compatible output field and is not the
  source of truth for individual provider outcomes.
- `data_source_modes` reports configured/requested modes. Actual provider
  success, no-record, failure, skipped, and cache-hit outcomes are reported in
  `provider_mode_summary`.
- 77B additionally emits the normalized provider runtime contract under
  `step_results.provider_runtime`; it is an audit/summary surface and not an
  evidence-generation surface.
- Online provider requests use live source-version labels by default unless a
  caller explicitly overrides the source version.

## Evidence Boundaries

- Providers do not create applied `EvidenceItem` records.
- ClinVar and ClinGen ERepo records are review-note/comparator context only.
- Literature records are candidate-only and reviewed-draft inputs only.
- gnomAD and VEP facts may only flow through existing population and
  computational evaluators.
- A no-record gnomAD result is limitation-only and must not trigger PM2.
- VEP missing predictors become limitations and must not directly generate
  PP3/BP4.
- Candidate evidence must not silently enter the combiner.

## Failure Handling

Provider failures are expected operational events. The pipeline records them as
limitations and continues:

- timeout;
- HTTP error;
- malformed JSON;
- parser uncertainty such as unparseable ClinVar date fields;
- empty provider result;
- missing source version or provenance;
- gnomAD no-record result;
- low AN or unknown coverage;
- population/build/ancestry mismatch;
- missing VEP predictor fields;
- abstract-only literature metadata.

No provider miss is treated as proof of absence unless a later, explicitly
reviewed workflow establishes that interpretation.

## Provenance Requirements

Every online provider result, including failures and misses, should preserve a
source envelope with:

- source version or live-source label;
- retrieval timestamp;
- normalized query;
- endpoint/source URL;
- parser version;
- raw snapshot hash;
- cache hit state where applicable;
- limitations.

ClinVar date provenance additionally preserves the raw `last_evaluated` value,
normalized date when available, parse status, and date precision. Year-only
dates remain reviewable as year-precision records; unknown or malformed dates
are limitations rather than provider failures.

The raw snapshot hash may refer to a structured failure or empty-result envelope
when no successful provider record was returned.

`provider_mode_summary` is the top-level audit view for this envelope. It
includes requested mode, configured mode, actual outcome, source version,
endpoint, query, raw hash, cache-hit state, provider mode, record count, and
limitations for ClinVar, population/gnomAD, computational/VEP,
literature/PubMed-LitVar, and ClinGen ERepo when included.

`step_results.provider_runtime` is the normalized 77B source for provider
outcome summaries. It adds attempted state, standardized outcome labels,
warnings, error summary fields, raw record hash, retrieval timestamp, and
structured provenance while preserving all raw provider step payloads.
