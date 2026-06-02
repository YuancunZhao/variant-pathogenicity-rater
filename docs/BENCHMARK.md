# Curated SNV/Small-Indel Benchmark

`data/benchmark_snv_cases.json` is an offline, curated mock benchmark for the
ACMG SNV/small-indel pipeline. It is not a clinical truth set and does not call
external services. Its purpose is regression testing for medical safety
behaviors: evidence separation, conservative VUS defaults, valid population
threshold context, ClinVar conflict handling, PVS1 edge-case restraint,
reviewed-evidence boundaries, ClinGen ERepo review-note behavior, VCEP
signal/override boundaries, provider limitations, and provenance expectations.

## Dataset Contents

The benchmark currently contains 100 cases:

- 5 pathogenic
- 4 likely pathogenic
- 76 VUS
- 7 likely benign
- 8 benign

Current dataset metadata:

- Benchmark version: `offline-curated-v4-phase-c`.
- Scope: 100 offline curated SNV/small-indel cases.
- Provider data: fixture-backed through `data/benchmark_provider_fixtures/`.
- Phase C fixture additions: local `annotation.jsonl` and
  `transcript_metadata.jsonl` for PVS1, splice, MANE, and transcript validation
  boundaries.
- Latest full regression status: `573 passed, 1 skipped`.

Each case includes gene, transcript, HGVS c./p., variant type, disease,
inheritance, mock population data, mock computational predictions, a mock
ClinVar record, mock literature evidence, expected classification, expected
applied evidence, expected candidate evidence, expected review flags, expected
limitations, and a rationale.

Phase A expanded the dataset from 21 to 40 cases. The added cases cover:

- generated applied `PVS1`, `PM2_Supporting`, `BA1`, `BS1`, `PP3`, `BP4`,
  `PS1`, and `PM5`;
- `PVS1` candidate-only behavior when LoF mechanism is unconfirmed;
- candidate-only isolation for ClinVar, computational, literature-draft, and
  VCEP-disabled evidence;
- curator-only `reviewed_applied` evidence using reviewed `PM3`;
- literature-suggested draft evidence that remains `needs_more_info`;
- ClinGen ERepo exact variant matches as review notes only;
- VCEP signal-only behavior and approved safe override behavior;
- provider limitation cases for population miss, ancestry mismatch, and low
  allele number.

Phase A kept provider facts embedded as inline local fixtures in the benchmark
case file. Phase B expanded the dataset from 40 to 70 cases and moved the new
provider facts into local JSONL fixtures under
`data/benchmark_provider_fixtures/`. Each Phase B case includes
`provider_fixture_refs` for population, ClinVar, computational, literature,
ClinGen ERepo, or VCEP profile context.

Phase B fixture references use the stable form `provider:case_id`, such as
`population:bench-41`. Phase C keeps that pattern through `bench-100` and adds
`annotation.jsonl` and `transcript_metadata.jsonl` for local PVS1, splice,
MANE, and transcript-boundary validation. The benchmark tests require every
external fixture reference to resolve, require fixture ids to match their owning
case ids, and fail on unused fixture rows. This keeps the benchmark as an
integrated local-provider regression set rather than a collection of
disconnected mock payloads.

Phase C is now the current benchmark baseline. It is still an offline
validation set, not a clinical truth set. It is intended to catch integration
regressions in applied evidence generation, provider limitation handling,
candidate/applied separation, provenance, and report-visible safety boundaries.

## Evidence Model

Population, computational, ClinVar, literature, ClinGen ERepo, VCEP profile,
manual reviewed evidence, and PVS1 evidence are evaluated through the normal
`rate_variant` pipeline. The benchmark also uses
`options.mock_supplemental_evidence_items` for curated local applied or
candidate evidence such as PS3, PS4, PM1, PM3, PM5, BS2, BS3, BP2, BP6, BP7,
and literature-style draft notes. These items are validated as normal
`EvidenceItem` records and then passed through the same candidate/applied
separation rules as runtime evidence; the expected classifications are not
hard-coded.

ClinVar, ClinGen ERepo, literature, VCEP signal, and draft reviewed evidence
remain candidate/review-note evidence unless the pipeline explicitly applies an
ACMG criterion through a validated evaluator or a curator supplies valid
`reviewed_applied` evidence. Candidate items must appear in the report's
`Candidate / Review-Note Evidence` section and must not change the final
classification.

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
- ClinVar comparator-based PS1 and PM5 application.
- ClinGen ERepo exact matches staying review-note only.
- VCEP signal-only profiles not changing evidence or classification.
- Approved VCEP overrides moving disabled generated criteria to candidate-only
  review notes with provenance.
- Reviewed-applied evidence entering classification only through explicit
  curator records.
- Literature suggested drafts staying `needs_more_info` and not counted.
- Provider misses, ancestry mismatch, and low allele number becoming
  limitations or candidate-only evidence rather than applied criteria.
- Phase B real-world style examples across BRCA1/BRCA2, CFTR, GJB2, PAH,
  TP53, cardiomyopathy genes, splice-edge variants, high-AF benign examples,
  ClinVar conflict/context mismatch, and rare PP3/BP4-only VUS cases.
- Phase C edge cases across last-exon/NMD/start-loss/canonical-splice PVS1
  boundaries, population threshold and provider-quality failures, computational
  conflict and SpliceAI-only cases, ClinVar PS1/PM5 comparator gates,
  ERepo/VCEP review-note and override behavior, reviewed evidence, literature
  drafts, and transcript/MANE validation boundaries.

The current benchmark coverage includes:

- `PVS1` applied, downgraded, and candidate-only paths.
- `BA1`, `BS1`, and `PM2_Supporting` population rule gates.
- `PP3` and `BP4` computational consensus and conflict gates.
- `PS1` and `PM5` ClinVar comparator gates.
- Manual `reviewed_applied`, `reviewed_rejected`, and `needs_more_info`
  evidence boundaries.
- Literature suggested-evidence drafts.
- ClinGen ERepo exact-match review-note behavior.
- VCEP signal-only and approved override behavior.
- Provider limitations for miss, low AN, ancestry mismatch, founder warning,
  genome-build mismatch, and missing thresholds.
- Transcript/MANE validation and transcript-dependent evidence blocking.
- Strict applied/candidate evidence separation.

## Expansion Strategy

The benchmark expansion is staged:

- Phase A: 21 to 40 cases, implemented, focused on applied-evidence and
  safety-boundary coverage.
- Phase B: 40 to 70 cases, implemented, broadening real-world style examples
  and moving the added provider facts into `data/benchmark_provider_fixtures/`.
- Phase C: 70 to 100 cases, implemented, adding broader PVS1 edge, population,
  computational, ClinVar PS1/PM5, ERepo/VCEP, reviewed-evidence, literature,
  and transcript/MANE coverage while staying fully offline.
- Phase D: 100+ cases, deferred; likely candidates include broader malformed
  provider payloads, stale-source provenance, more condition-specific VCEP
  conflict cases, and report-smoke expansion.

Current known gaps outside this benchmark baseline:

- Real online provider smoke gates are optional and not part of default CI.
- A selected real VCEP profile pilot has not been implemented.
- Chinese report templates are implemented for laboratory-internal reports, but
  broader localization review and site-specific sign-out wording remain outside
  this benchmark baseline.
- Larger real-world hospital annotation validation has not been completed.
- CNV/SV interpretation is not supported.

Recommended next validation/product tasks:

- Chinese report template with safety-language parity.
- Selected real-world SNV/small-indel case validation.
- Selected real VCEP profile pilot behind explicit activation.
- Optional online smoke gates for provider reachability and parser resilience.

The ACMG classification combiner must remain unchanged during benchmark
expansion. Benchmark expectations are regression expectations for the current
conservative pipeline and must not be treated as clinical truth assertions.
Expected applied and candidate evidence are checked separately and strictly,
including evidence strength, so candidate/review-note evidence cannot satisfy
an applied-evidence expectation.

Run the benchmark regression suite with:

```bash
.venv/bin/python -m pytest tests/test_benchmark_dataset.py
```
