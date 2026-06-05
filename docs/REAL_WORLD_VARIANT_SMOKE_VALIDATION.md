# Real-World Variant Smoke Validation

This validation layer exercises a small set of real HGVS c. inputs through the
existing VPR `rate_variant` pipeline. It is a smoke validation suite, not a
clinical truth benchmark.

## Scope

The v1 dataset is `data/real_world_smoke_variants_v1.json` and contains six
real-world HGVS-like inputs:

| Case | Input |
| --- | --- |
| `real-world-smoke-pklr-c1403c-g` | `PKLR;NM_000298.6:c.1403C>G` |
| `real-world-smoke-myh7-c5347a-t` | `MYH7;NM_000257.4:c.5347A>T` |
| `real-world-smoke-flg-c12064a-t` | `FLG;NM_002016.2:c.12064A>T` |
| `real-world-smoke-aifm1-c1030c-t` | `AIFM1;NM_004208.4:c.1030C>T` |
| `real-world-smoke-gamt-c268g-a` | `GAMT;NM_000156.6:c.268G>A` |
| `real-world-smoke-hlcs-c1063-1064del` | `HLCS;NM_001352514.2:c.1063_1064del` |

The suite intentionally does not define `expected_classification` and does not
evaluate final classification accuracy. Its purpose is to verify that real
HGVS inputs return structured, auditable results without changing evidence
generation, safety rules, or the ACMG classification combiner.

## Offline Default

`tests/test_real_world_variant_smoke_validation.py` runs by default with local
mock/offline providers. The default path must not use the network. The test
asserts:

- each case returns either `status=ok` or a structured `status=error`;
- normalization/provider/runtime/evidence state remains inspectable;
- canonical output sections are present: `input`, `variant`, `runtime`,
  `providers`, `evidence`, `classification`, `review`, and `limitations`;
- legacy compatibility fields remain present: `final_classification`,
  `normalized_variant`, `variant_resolution`, `applied_evidence`, and
  `candidate_evidence`;
- any structured error must include limitations and `human_review_required`;
- unresolved protein, coordinate, and transcript counts can be summarized.

At the time this validation was added, the offline smoke path returns
`status=ok` for all six cases. The expected limitations are unresolved
protein/coordinate/transcript mapping for HGVS-only inputs, with the HLCS
deletion also surfacing unresolved deletion ref/alt limitations unless a
genomic anchor is supplied.

## Natural-Language Smoke

The suite also runs one text-wrapper smoke case:

```text
PKLR NM_000298.6:c.1403C>G
```

This verifies that `rate_variant_from_text` preserves `input.original_input`,
`input.parsed_input`, and the nested structured `rate_variant` result without
crashing. The text wrapper is still only an input wrapper and does not generate
ACMG evidence or change classification logic.

## Optional Online Smoke

Optional real-world online provider smoke is env-gated and skipped by default:

```bash
VPR_RUN_REAL_WORLD_ONLINE_SMOKE=1 \
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache \
.venv/bin/python -m pytest tests/test_real_world_variant_smoke_validation.py -q
```

The online path may request online ClinVar, gnomAD, and Ensembl VEP providers
through existing opt-in runtime flags. It only summarizes provider outcomes and
does not evaluate classification accuracy. Provider misses, endpoint failures,
or parser failures must remain visible as provider outcomes, limitations, or
review flags instead of crashing the pipeline.

## Validation Commands

Targeted validation:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest \
  tests/test_real_world_variant_smoke_validation.py \
  tests/test_rate_variant_pipeline.py \
  tests/test_natural_language_input.py \
  -q
```

Full validation:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest
```
