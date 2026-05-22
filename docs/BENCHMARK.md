# Curated SNV/Small-Indel Benchmark

`data/benchmark_snv_cases.json` is an offline, curated mock benchmark for the
phase-1 ACMG SNV/small-indel pipeline. It is not a clinical truth set and does
not call external services. Its purpose is regression testing for medical safety
behaviors: evidence separation, conservative VUS defaults, valid population
threshold context, ClinVar conflict handling, and PVS1 edge-case restraint.

## Dataset Contents

The benchmark currently contains 21 cases:

- 4 pathogenic
- 4 likely pathogenic
- 5 VUS
- 4 likely benign
- 4 benign

Each case includes gene, transcript, HGVS c./p., variant type, disease,
inheritance, mock population data, mock computational predictions, a mock
ClinVar record, mock literature evidence, expected classification, expected
applied evidence, expected candidate evidence, expected review flags, and a
rationale.

## Evidence Model

Population, computational, ClinVar, literature, and PVS1 evidence are evaluated
through the normal `rate_variant` pipeline. The benchmark also uses
`options.mock_supplemental_evidence_items` for curated local applied evidence
such as PS3, PS4, PM1, PM3, PM5, BS2, BS3, BP2, BP6, and BP7. These items are
validated as normal `EvidenceItem` records and then passed to the ACMG combiner;
the expected classifications are not hard-coded.

ClinVar and literature evidence remain candidate/review-note evidence unless the
pipeline explicitly applies an ACMG criterion through an evaluator. Candidate
items must appear in the report's `Candidate / Review-Note Evidence` section and
must not change the final classification.

## Safety Scenarios

The regression tests cover:

- PVS1 plus PM2_Supporting and PP3 reaching pathogenic when context is valid.
- PM2 alone remaining VUS.
- PP3 alone remaining VUS.
- PM2 plus PP3 remaining VUS.
- BA1 applying as benign only with disease-specific threshold and penetrance
  context.
- BS1 contributing to likely benign only with valid threshold context.
- ClinVar conflicting interpretations requiring review.
- Candidate literature/ClinVar evidence not affecting classification.
- PVS1 start-loss edge cases staying candidate-only.
- Opposing pathogenic and benign evidence defaulting to VUS.

Run the benchmark regression suite with:

```bash
.venv/bin/python -m pytest tests/test_benchmark_dataset.py
```
