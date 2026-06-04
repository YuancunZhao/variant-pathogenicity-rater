# Live Provider Smoke Validation

Live provider smoke validation checks the opt-in online provider layer for
reachability, payload compatibility, cache/provenance behavior, and safe
failure degradation. It is not a default test suite, not clinical validation,
and not a source of autonomous ACMG classification.

## Environment Gate

All live smoke tests are skipped unless the global gate is set:

```bash
VPR_RUN_LIVE_PROVIDER_SMOKE=1
```

Optional runtime settings:

```bash
VPR_LIVE_PROVIDER_CACHE_DIR=/tmp/vpr_live_provider_cache
VPR_LIVE_PROVIDER_TIMEOUT=10
VPR_LIVE_PROVIDER_EMAIL=you@example.org
VPR_LIVE_PROVIDER_USER_AGENT="variant-pathogenicity-rater live smoke"
```

LitVar is treated as optional and experimental. Its live endpoint smoke is
skipped unless both gates are set:

```bash
VPR_RUN_LIVE_PROVIDER_SMOKE=1
VPR_RUN_LIVE_LITVAR_SMOKE=1
```

The cache directory does not enable online behavior by itself. Online retrieval
still requires explicit provider flags in CLI/MCP calls or explicit online
provider configuration in tests.

## Test Command

Default offline validation remains:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest
```

Optional live smoke validation:

```bash
VPR_RUN_LIVE_PROVIDER_SMOKE=1 \
VPR_LIVE_PROVIDER_CACHE_DIR=/tmp/vpr_live_provider_cache \
VPR_LIVE_PROVIDER_TIMEOUT=10 \
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache \
.venv/bin/python -m pytest tests/test_live_provider_smoke.py -m "online_clinvar_smoke or online_gnomad_smoke or online_vep_smoke or online_literature_smoke"
```

Live smoke tests may pass with provider records or with structured limitations.
Network timeouts, provider misses, malformed payloads, endpoint changes, and
empty results are acceptable smoke outcomes only when they are captured as
limitations and do not crash the workflow.

## Provider Checks

ClinVar EUtils smoke queries ALPL `NM_000478.6:c.305A>C`. A successful response
must normalize to `ClinVarRecord` with clinical significance, review status or
review confidence, and provenance. A miss or retrieval failure must become a
limitation. ClinVar records may produce candidate review notes with
`strength=none` and `applied=false`, but must not create applied PP5/BP6.
ClinVar `last_evaluated` values may use provider-specific formats such as
`2025/08/29`; smoke validation expects these to normalize without
`Invalid isoformat` failures while preserving the raw date and precision in
provenance.

gnomAD GraphQL smoke queries GRCh38 `1-21563117-A-C`. A successful response may
include AC, AN, AF, population, FAF, or homozygote/hemizygote fields. A
no-record response is a limitation only, keeps `is_absent=false`, and must not
trigger PM2 from absence inference.

Ensembl VEP REST smoke queries `1:21563117 A>C`. A successful response should
provide transcript, consequence, HGVS protein, or supported predictor fields
when available. Missing predictor fields must be reported as limitations. VEP
records do not directly apply PP3/BP4; any applied computational evidence must
come only through the existing computational evaluator.

PubMed EUtils smoke queries PMID `36361766` and ALPL variant context. A
successful response must normalize to `LiteratureRecord` metadata with PMID,
title, source, query, timestamp, and provenance. PubMed ESummary may be
metadata-only; abstract-missing or abstract-only limitations are acceptable.
Literature output remains candidate-only and reviewed-draft material only.

LitVar smoke is optional/experimental. When enabled, it must normalize any
available records into `LiteratureRecord` with candidate-only provenance. If
the endpoint is unavailable or payload shape changes, the test must record
limitations rather than treating the failure as classification evidence.

## Cache And Provenance

Smoke validation checks that online provider results preserve:

- source name and source version or live-source label;
- retrieval timestamp;
- normalized query;
- endpoint, source URL, or request URL;
- parser version;
- raw payload or raw record hash;
- provider mode;
- cache hit state;
- limitations where applicable.

For ALPL online flow review, the expected safety behavior is: ClinVar records
enter `query_clinvar` step results and candidate/review-note output only;
gnomAD uses variant ID `1-21563117-A-C` and no-record responses remain
limitation-only; VEP uses the region allele representation for
`1:21563117 A>C` and unsupported/missing predictors remain visible in
computational step results; PubMed records feed literature summaries and drafts
only.

Cache smoke performs an initial request with `cache_hit=false`, then repeats the
same query and expects `cache_hit=true` without a second HTTP request when the
cache key is unchanged.

## Safety Assertions

Live provider smoke tests preserve the existing evidence boundary:

- default pytest and CI remain offline;
- provider failures, timeouts, malformed payloads, and no-record results become
  limitations, not crashes;
- no provider directly creates applied evidence;
- ClinVar does not auto-trigger PP5/BP6;
- PubMed and LitVar do not create applied literature evidence;
- gnomAD no-record responses do not trigger PM2;
- VEP missing predictors do not directly trigger PP3/BP4;
- MCP online options remain schema-compatible for Codex clients;
- the ACMG classification combiner remains unchanged.
