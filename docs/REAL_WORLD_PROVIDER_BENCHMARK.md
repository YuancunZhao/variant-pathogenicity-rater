# Real-World Provider Benchmark

78C adds a provider benchmark for the six real-world HGVS cases introduced in
78A and improved by 78B. This is a provider-yield and observability benchmark,
not an ACMG classification benchmark.

## Dataset

Dataset: `data/provider_benchmark/provider_benchmark_v1.json`

Cases: 6 variants

- `PKLR NM_000298.6:c.1403C>G`
- `MYH7 NM_000257.4:c.5347A>T`
- `FLG NM_002016.2:c.12064A>T`
- `AIFM1 NM_004208.4:c.1030C>T`
- `GAMT NM_000156.6:c.268G>A`
- `HLCS NM_001352514.2:c.1063_1064del`

The dataset records expected 78B local resolution availability for coordinate
and protein fields. These expectations are used only for coverage metrics.

## Runner

Python API:

```python
from variant_pathogenicity_rater.benchmark import run_provider_benchmark

result = run_provider_benchmark(
    use_online=True,
    include_litvar=False,
    provider_cache_dir="/tmp/vpr_provider_benchmark_cache",
    provider_timeout=10,
)
```

The result is `ProviderBenchmarkResult` and includes:

- `dataset_size`
- provider outcome metrics for `clinvar`, `gnomad`, `vep`, `pubmed`, `litvar`
- provider-yield metrics
- provider runtime/cache/timeout metrics
- resolution coverage before/after provider execution
- provider identity coverage metrics:
  `gnomad_variant_id_available`, `identity_conflict_count`,
  `coordinate_available`, and `protein_available`
- per-case provider runtime payloads
- summary and limitations

The benchmark reads provider runtime output from the pipeline but does not
write to `rate_variant` output, `classification_result`, or evidence items.
79A-1 additionally reads additive provider-layer `provider_identity` output for
identity coverage. These metrics are provider-readiness audit fields only and
do not change provider calls, classification, or evidence generation.

CLI:

```bash
vpr provider-benchmark \
  --dataset data/provider_benchmark/provider_benchmark_v1.json \
  --output-md /tmp/vpr_provider_benchmark_reports/provider_benchmark_report.md \
  --output-json /tmp/vpr_provider_benchmark_reports/provider_benchmark_result.json
```

The CLI is offline by default. Add `--online` only when a live benchmark is
intended:

```bash
vpr provider-benchmark \
  --online \
  --provider-cache-dir /tmp/vpr_provider_benchmark_cache \
  --timeout 15 \
  --include-litvar \
  --output-md /tmp/vpr_provider_benchmark_reports/provider_benchmark_report.md \
  --output-json /tmp/vpr_provider_benchmark_reports/provider_benchmark_result.json
```

The command prints a compact JSON summary to stdout and writes optional
Markdown/JSON artifacts when output paths are provided.

## Provider Metrics

Each provider records:

- `success`
- `no_record`
- `failure`
- `partial`
- `skipped`

`population` runtime is reported as `gnomad`, and `computational` runtime is
reported as `vep`. Literature runtime is split into PubMed and LitVar benchmark
surfaces for reporting and yield metrics.

## Yield Metrics

ClinVar:

- `records_found`
- `candidate_evidence_generated`

gnomAD:

- `af_records_found`
- `population_provider_hits`

VEP:

- `consequence_resolved`
- `predictor_records_returned`

PubMed:

- `articles_found`
- `summary_generated`

LitVar:

- `citations_found`

These are benchmark metrics only. They do not become ACMG evidence and do not
change candidate/applied evidence boundaries.

## Runtime And Cache Metrics

For each provider:

- `avg_latency_ms`
- `median_latency_ms`
- `latency_scope`
- `provider_latency_count`
- `case_level_latency_used_count`
- `timeout_count`
- `cache_hit_count`
- `cache_miss_count`

`latency_scope` is `provider` when the pipeline/provider payload contains an
explicit provider runtime sample, `case` when the benchmark had to fall back to
the enclosing case runtime, `mixed` when both are present, and `unavailable`
when no attempted provider runtime can be measured. Case-level fallback latency
is retained for smoke observability but must not be interpreted as
provider-specific timing.

Provider failures and timeouts are captured as benchmark results and
limitations. They must not crash benchmark execution.

## Identity Gating Summary

79A-2 separates provider dependency skips from true provider failures. Benchmark
outcome metrics now include:

- `dependency_skipped`
- `invalid_identity`
- `missing_identity`

For gnomAD, invalid or missing provider-layer identity is counted as a skipped
dependency before GraphQL is called. It is not counted as `failure` and is not
counted as `no_record`. gnomAD `no_record` is used only after a valid query
executes and returns no matching variant.

## Provider Diagnostics

78D/78E harden the provider observability path used by this benchmark:

- gnomAD GraphQL `errors` are classified as provider `failure`, not
  `no_record`; HTTP status/body summaries and request payload hashes are
  retained in the raw provenance payload.
- 78E identifies current gnomAD schema drift in the legacy optional
  `populations` and `faf95` fields. The provider now attempts a full query,
  falls back to a stable exome/genome frequency query, and finally falls back
  to a minimal identity query.
- gnomAD provenance records the dataset, variant ID, endpoint, GraphQL query
  name/version, request payload hash, HTTP status, and bounded response-body or
  GraphQL-error summaries for failed attempts.
- gnomAD `no_record` remains limitation-only and is not treated as population
  absence or PM2 support.
- 78F stabilizes Ensembl VEP by trying POST region first for normalized
  coordinates, then GET region with the alt-only allele representation, then
  transcript HGVS fallback when an HGVS c. query is available. Each
  representation tries predictor-enriched parameters before a minimal
  consequence-only fallback.
- VEP attempt diagnostics retain method, endpoint, request URL or payload hash,
  HTTP status, bounded response-body summaries, timeout state, selected variant
  representation, transcript/HGVS context, and the final fallback outcome.
- VEP missing predictors remain limitations and do not directly generate
  PP3/BP4.
- PubMed expands from gene+HGVS to aliases/protein consequence, gene+disease,
  and the existing query plan; ClinVar/caller-supplied citation PMIDs are used
  only after search terms return no records.

Benchmark summaries include per-provider failure case IDs, no-record case IDs,
dependency-skipped case IDs, gnomAD invalid-identity skip case IDs, and the
first error examples with `error_type` and `error_message_summary`.

## Optional Live Benchmark

The live benchmark is skipped by default. Run it only with an explicit
environment gate:

```bash
VPR_RUN_PROVIDER_BENCHMARK=1 \
VPR_PROVIDER_BENCHMARK_OUTPUT_DIR=/tmp/vpr_provider_benchmark_reports \
VPR_PROVIDER_BENCHMARK_TIMEOUT=10 \
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache \
.venv/bin/python -m pytest tests/test_real_world_provider_benchmark.py -q
```

When `VPR_PROVIDER_BENCHMARK_OUTPUT_DIR` is set, the env-gated test writes:

- `provider_benchmark_report.md`
- `provider_benchmark_result.json`

LitVar can be included explicitly:

```bash
VPR_RUN_PROVIDER_BENCHMARK=1 \
VPR_RUN_PROVIDER_BENCHMARK_LITVAR=1 \
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache \
.venv/bin/python -m pytest tests/test_real_world_provider_benchmark.py -q
```

## Offline Test Coverage

Default pytest validates the benchmark contract without network access:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest \
  tests/test_provider_benchmark.py \
  tests/test_real_world_provider_benchmark.py \
  -q
```

The offline tests cover success, no-record, partial, failure, timeout,
cache-hit, cache-miss, latency scope, provider diagnostics, CLI Markdown/JSON
artifact generation, report generation, and classification isolation.

## Safety

- The ACMG combiner is unchanged.
- Evidence generation logic is unchanged.
- Candidate/applied evidence boundaries are unchanged.
- Provider metrics do not change final classification.
- Live provider execution remains opt-in and env-gated.
