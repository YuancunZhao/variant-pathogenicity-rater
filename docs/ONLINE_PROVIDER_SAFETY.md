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

The raw snapshot hash may refer to a structured failure or empty-result envelope
when no successful provider record was returned.
