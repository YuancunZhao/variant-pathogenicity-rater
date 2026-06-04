# Real Provider Pipeline

The real provider pipeline adds opt-in online adapters for ClinVar, gnomAD,
Ensembl VEP, PubMed, and LitVar. These adapters retrieve and normalize provider
records into the existing Variant Pathogenicity Rater data-source layer.

Online providers are disabled by default. Default test and CLI behavior remains
offline/mock/local and does not require network access.

Status: implemented and integration-reviewed. The latest offline integration
review completed with `655 passed, 2 skipped`; optional live smoke validation is
implemented in `tests/test_live_provider_smoke.py`, remains env-gated, and is
skipped by default. See `docs/LIVE_PROVIDER_SMOKE_VALIDATION.md`.

The 76 mock/fixture interface audit activation clarified runtime mode reporting
without changing evidence logic. `mock_mode` remains in outputs for backward
compatibility. `data_source_modes` reports configured/requested modes after
runtime options are applied, while `provider_mode_summary` reports actual
provider outcomes such as success, no record, failure, skipped, or cache hit.
`offline_default_mode` records the default-off posture, and
`unresolved_placeholder_mode` flags unresolved resolution/provider placeholder
states.

The 77A output schema unification adds an additive canonical output view on top
of these fields. New clients should read provider state from
`providers.summary` and runtime state from `runtime`, while the legacy
`provider_mode_summary`, `mock_mode`, `data_source_modes`,
`offline_default_mode`, and `unresolved_placeholder_mode` fields continue to be
emitted for compatibility. See `docs/OUTPUT_SCHEMA.md`.

The 77B provider interface consolidation adds a shared provider runtime
contract under `step_results.provider_runtime`. `provider_mode_summary` and
canonical provider entries are now built from this normalized adapter layer
rather than directly depending on ad hoc pipeline-side interpretation of
heterogeneous provider steps. Provider internals and raw step payloads remain
unchanged.

## Architecture

Online providers are fact providers, not ACMG classifiers:

- ClinVar online records normalize to `ClinVarRecord`.
- gnomAD online records normalize to `PopulationFrequency`.
- Ensembl VEP online records normalize to computational prediction and
  transcript/consequence records.
- PubMed and LitVar online records normalize to literature-engine
  `LiteratureRecord` records.

The ACMG classification combiner is unchanged. Provider output can affect
classification only through existing safety-gated evaluators:

- population facts through population rules;
- computational facts through PP3/BP4 computational rules;
- ClinVar comparator facts through PS1/PM5 comparator generation;
- literature records through candidate-only literature summaries and reviewed
  drafts.

ClinVar assertions, ClinGen ERepo records, and literature records remain
non-applied unless a curator later submits valid `reviewed_applied` evidence.

## Providers

### ClinVar

The ClinVar online provider uses NCBI EUtils query shapes for Variation ID,
rsID, HGVS, genomic coordinates, and comparator-oriented gene queries. It
normalizes review status, star level, condition, germline/somatic context,
clinical significance, submitter count, last evaluated date, conflict status,
citations, and provenance into `ClinVarRecord`.

ClinVar date parsing accepts common ISO, slash, dot, English month, and
year-only `last_evaluated` formats. Day-precision dates normalize to
`YYYY-MM-DD`; year-only dates normalize to `YYYY-01-01` with
`last_evaluated_precision=year` in provenance. Unknown or malformed dates
become limitations and do not fail the provider query.

ClinVar never emits applied PP5/BP6. Exact records are review notes, and
same-residue or same-amino-acid records can only support PS1/PM5 through the
existing comparator generator.

### gnomAD

The gnomAD online provider uses GraphQL variant lookup and maps AC, AN, AF,
homozygote/hemizygote counts, population counts, popmax, FAF, dataset version,
and query provenance into `PopulationFrequency`.

A missing gnomAD record is a limitation only. It is not interpreted as
population absence and cannot trigger PM2 by itself.

When online gnomAD is requested, source labels default to
`gnomAD gnomad_r4 live GraphQL` unless the caller explicitly supplies a source
version. The provider summary exposes the normalized gnomAD variant ID query,
for example `1-21563117-A-C`.

### Ensembl VEP

The Ensembl VEP online provider parses transcript consequences, HGVS
protein/coding/genomic fields where available, protein consequence,
canonical/MANE-like tags when present in the payload, and supported predictor
fields including CADD, REVEL, SIFT, PolyPhen, MutationTaster, AlphaMissense,
and SpliceAI.

Missing predictors become limitations. VEP does not directly apply PP3/BP4.
VEP transcript consequences may also populate descriptive
`variant_resolution.resolved_hgvs_p` and consequence fields when local
resolution fixtures are missing. This bridge is scoped to variant resolution
only and does not create evidence or bypass the computational evaluator.

### PubMed and LitVar

PubMed and LitVar online adapters feed the General Literature Search and
Summary Engine. They retrieve metadata and abstracts where available, preserve
provider provenance, and mark abstract-only records as requiring manual review.

Literature output remains suggested/reviewed-draft material only. It is never
added to applied ACMG evidence automatically.

## Audit Data

Provider outputs preserve:

- provider/source name;
- source version or live-source label;
- retrieval timestamp;
- normalized query;
- endpoint or source URL;
- parser version;
- raw payload hash;
- cache hit status when available;
- limitations and review flags.

`provider_mode_summary` repeats these audit fields per provider, including
requested mode, configured mode, actual outcome, source version, endpoint,
query, raw hash, cache hit, provider mode, record count, and limitations.
Canonical `providers.summary` mirrors this provider outcome summary, and
per-provider canonical entries normalize requested/configured mode, attempted
state, outcome, record count, source version, query, endpoint, cache hit,
limitations, and provenance.
77B also exposes additive runtime fields such as `attempted`, `outcome`,
`warnings`, `error_type`, `error_message_summary`, `raw_record_hash`,
`retrieval_timestamp`, and raw `provenance`.
Online provider attempts use live source labels by default; they should not
surface `offline-fixture-v1` unless the caller explicitly configured a local or
fixture source.

Provider failures, timeouts, malformed responses, empty results, low-quality
population data, build mismatch, ancestry mismatch, stale source metadata, and
unsupported predictor fields degrade to limitations instead of aborting the
main workflow.

Provider parser uncertainty, including unparseable ClinVar dates, is retained
as provenance and limitations. Parser limitations do not promote candidate
evidence and do not change classification directly.

## Integration Review Boundary

The completed pipeline preserves these reviewed safety outcomes:

- default `rate`, `rate-text`, batch, annotated-batch, and MCP workflows do not
  send HTTP requests;
- live provider smoke tests require `VPR_RUN_LIVE_PROVIDER_SMOKE=1` and remain
  outside default pytest/CI;
- provider online modes require explicit CLI flags or MCP options;
- cache hits avoid repeated provider requests and mark `cache_hit=true` in
  provenance where available;
- ClinVar online remains review-note/comparator context and never triggers
  PP5/BP6;
- PubMed/LitVar online surfaces feed literature suggestions and reviewed
  drafts only, never applied evidence;
- gnomAD online facts reach classification only through the existing
  population evaluator;
- Ensembl VEP facts reach classification only through the existing
  computational evaluator;
- a no-record gnomAD result is a limitation and does not trigger PM2;
- candidate/review-note evidence does not silently enter the combiner.
