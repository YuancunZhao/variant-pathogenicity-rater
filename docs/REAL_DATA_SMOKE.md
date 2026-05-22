# Real-Data Smoke Tests

The real-data smoke suite exercises the full `rate_variant` pipeline with a small
offline set of manually curated SNV/small indel examples. It is intended to catch
unsafe or unstable behavior, not to prove concordance with ClinVar.

## Goals

- Run representative real-variant examples without network access.
- Simulate ClinVar and population observations from local fixtures only.
- Keep ClinVar assertions out of final ACMG classification logic.
- Verify applied evidence and candidate/review-note evidence remain separated.
- Prefer conservative outcomes when evidence is sparse, conflicting, or edge-case.

## Files

- `data/real_data_smoke_cases.json` defines the curated cases, expected behavior,
  expected evidence, allowed classifications, review flags, and rationale.
- `data/fixtures/clinvar_smoke.jsonl` contains local ClinVar-like records used by
  the existing offline ClinVar provider.
- `data/fixtures/population_smoke.jsonl` contains local population-frequency-like
  records used by the existing offline population provider.
- `tests/test_real_data_smoke.py` loads the case set and fixtures, constructs a
  normal `rate_variant` payload, and validates pipeline output.

## Covered Scenarios

The initial smoke set contains 10 cases:

- 2 high-confidence P/LP LoF-style positive controls.
- 2 high-allele-frequency benign controls.
- 2 ClinVar conflicting-interpretation controls.
- 2 VUS controls.
- 1 PM2 + PP3 case that must remain VUS.
- 1 PVS1 edge case that must not be overcalled.

## Safety Expectations

The suite deliberately checks the conservative behavior of the system:

- ClinVar-derived PP5/BP6 records are candidate/review-note evidence only.
- ClinVar records must not appear in the applied evidence report section.
- A missing population fixture produces an unavailable frequency result and must
  not infer absence or trigger PM2.
- PM2 + PP3 alone remains VUS.
- PVS1 start-loss/edge-case evidence remains candidate-only when manual review is
  required.
- Opposing applied pathogenic and benign evidence defaults to VUS with a blocking
  review flag.

## Running

```bash
.venv/bin/python -m pytest tests/test_real_data_smoke.py
```

The full suite can be run with:

```bash
.venv/bin/python -m pytest
```

No test in this smoke framework should call ClinVar, gnomAD, or any other live
service. If a case is uncertain, set `allowed_classifications` conservatively
instead of weakening pipeline safety logic.
