# Online Provider Safety

Online provider support is an opt-in retrieval layer. It does not change the
ACMG combiner, does not relax evidence safety rules, and does not authorize
autonomous clinical interpretation.

## Default-Off Rules

- Online ClinVar, gnomAD, Ensembl VEP, PubMed, and LitVar are disabled by
  default.
- Default pytest must not require network access.
- Optional live smoke tests require provider-specific environment gates and
  are skipped by default.
- CLI and MCP online flags set `online_enabled=true` only for the requested
  provider.

## Evidence Boundaries

- Providers do not create applied `EvidenceItem` records.
- ClinVar and ClinGen ERepo records are review-note/comparator context only.
- Literature records are candidate-only and reviewed-draft inputs only.
- gnomAD and VEP facts may only flow through existing population and
  computational evaluators.
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
