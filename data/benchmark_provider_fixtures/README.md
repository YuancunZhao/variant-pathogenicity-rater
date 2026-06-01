# Benchmark Provider Fixtures

This directory stores offline benchmark provider snapshots.

Phase A keeps provider facts embedded in `data/benchmark_snv_cases.json` as
inline local fixtures because the benchmark runner already validates those
fixtures through the normal mock/local provider path. Each Phase A case includes
`provider_fixture_refs` that identify the inline fixture used for population,
ClinVar, computational, literature, ClinGen ERepo, or VCEP profile context.

Phase B moves the newly added provider records into JSONL files in this
directory and keeps the benchmark case file as a manifest with stable fixture
references.

Files:

- `population.jsonl`: population frequency records used by Phase B cases.
- `clinvar.jsonl`: ClinVar exact/comparator/conflict records.
- `computational.jsonl`: calibrated computational prediction fixtures.
- `literature.jsonl`: local literature records.
- `clingen_erepo.jsonl`: ClinGen Evidence Repository exact-match fixtures.
- `vcep_profile.jsonl`: local VCEP signal and override profile fixtures.

Each line has this shape:

```json
{"fixture_id": "bench-41", "record": {}}
```

Benchmark cases reference records with `provider_fixture_refs`, for example
`"population": "population:bench-41"`.
