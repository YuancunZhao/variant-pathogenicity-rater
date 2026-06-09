# 63A — Selected Real-World Case Validation Scaffold

## Purpose

Offline fixture-backed validation that exercises completed provider boundaries
— ProviderExecutionPlan observability, ProviderRuntimeResult provenance, and
candidate/applied evidence safety invariants — without changing classification
or provider execution behavior.

## Scope

- **6 selected cases** covering structured coordinate, ClinVar candidate-only,
  computational inline, literature candidate/review-note, absent-population PM2
  safety gate, and ClinGen ERepo candidate-only paths.
- **Offline only** — all cases run with `mock_mode=True`; no live network calls.
- **Invariant-focused** — tests validate provider runtime/plan/dependency/safety
  boundaries, not final classification correctness.

## Case list

| Case ID | Scenario | What it exercises |
|---------|----------|-------------------|
| `63A-brca1-structured-population` | Structured coordinate + population | PVS1 + PM2 applied; PP3/PP5 candidate-only |
| `63A-clinvar-candidate-only` | ClinVar conflict candidate-only | Conflicting ClinVar → PP5 candidate-only, never BP6/PP5 direct |
| `63A-computational-inline` | Computational inline predictions | PP3 applied from inline REVEL/CADD; PM2 from absent pop |
| `63A-literature-candidate` | Literature candidate/review-note | Literature records generate candidate evidence only |
| `63A-no-population-no-pm2` | Absent population → no PM2 | Missing population ≠ population absence; PM2 must not trigger |
| `63A-erepo-candidate` | ClinGen ERepo candidate-only | ERepo records generate review-note evidence only |

## Invariants checked

Per case:
- `status == ok`
- `mock_mode == True`, `offline_default_mode == True`
- `provider_execution_plan` exists and validates (plan_version, nodes, identity, summary)
- `provider_runtime` exists with valid outcomes for included providers
- `provider_dependency_checks` match plan dependency_check payloads
- `providers.summary` consistent with legacy `provider_mode_summary`
- No direct PP5/BP6 from ClinVar provider facts (must be candidate-only)
- All candidate items preserve `candidate_only`/`strength=none`/`applied=False` flags
- PM2 never triggered from absent population fixture
- Classification within allowed set (permissive: typically `["vus"]`)

## Important caveat on expected evidence and classifications

The `expected_applied_evidence`, `expected_candidate_evidence`, and
`allowed_classifications` fields in the case fixture are **fixture-backed
current-pipeline regression expectations**, not clinical truth assertions.
They record what the pipeline currently generates with the supplied
fixtures and should be updated when the pipeline's evidence generation
changes for legitimate reasons (e.g., new evidence generators, improved
context handling). They do not constitute a second source of ACMG truth
and must not be interpreted as "correct" or "clinically validated" output.

## What is intentionally not asserted

- Final classification correctness beyond membership in `allowed_classifications`
- Clinical validity of any evidence code assignment
- ACMG combiner scoring weights
- Evidence strength granularity (supporting/moderate/strong/very-strong)
- Network provider response shapes
- Online-only dependency skip behavior (all mock-mode)
- Full real-world coverage — this is a scaffold, not exhaustive validation

## How to run

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest -q \
  tests/test_selected_real_world_case_validation.py
```

## Fixture dependencies

- `data/selected_real_world_validation_cases.json` — case definitions
- `data/fixtures/population_smoke.jsonl` — population frequency fixtures
- `data/fixtures/clinvar_smoke.jsonl` — ClinVar record fixtures
- Inline `computational_predictions`, `literature_records`, `clingen_erepo_records` defined per case

## Safety boundaries preserved

- `combiner.py` is never modified
- ACMG evidence generation unchanged
- Candidate/applied safety gates unchanged
- Reviewed evidence validation unchanged
- Default offline/no-network behavior unchanged
- `ProviderRuntimeResult` remains sole runtime outcome source
- `ProviderExecutionPlan` remains observability-only
