# Current Roadmap

This roadmap is the governance-facing roadmap for Variant Pathogenicity Rater.
It should be read with `docs/PROJECT_STATE.md`, `docs/KNOWN_LIMITATIONS.md`,
`docs/APPLIED_EVIDENCE_GENERATION.md`, and
`docs/APPLIED_EVIDENCE_STATUS.md` before planning future work.

The current roadmap priority is not to broaden the clinical surface quickly. It
is to harden the completed interpretation loop while preserving the existing
safety architecture: candidate-only evidence remains outside the combiner,
applied evidence remains review-required, online behavior remains opt-in,
reviewed evidence requires explicit curator action, and failures remain
limitations.

## Completed Phases

### Phase 1: PVS1

The PVS1 phase established conservative SNV/small-indel loss-of-function
evidence generation. It introduced consequence and HGVS LoF parsing, LoF
mechanism resolution, transcript relevance checks, NMD and terminal-exon
assessment, splice-specific handling, a conservative decision tree, and
conversion into applied `EvidenceItem` records.

The important architecture lesson from Phase 1 is that PVS1 is not applied from
variant consequence labels alone. Disease mechanism, transcript relevance,
NMD/splice context, limitations, and manual review remain part of the safety
contract.

### Phase 2: Population

The population phase added conservative generation for `BA1`, `BS1`, and
`PM2_Supporting`. Population decisions require disease-specific threshold
context, appropriate penetrance and ancestry assumptions, source/version
provenance, compatible genome build, adequate allele number and coverage, and
no blocking context conflict.

This phase established that a provider miss is not evidence of absence. Missing
or low-quality frequency data becomes unavailable or limitation-only; it does
not automatically trigger PM2.

### Phase 3: Computational

The computational phase added consensus-based `PP3` and `BP4` generation.
These criteria are supporting-only, review-required, blocked by predictor
conflict, and inappropriate for contexts such as frameshift/nonsense/CNV/SV
where missense-style predictors would double-count or misrepresent evidence.

This phase also formalized that SpliceAI and similar predictors provide
computational splice support only. They are not RNA validation, functional
assay evidence, `PS3`, `BS3`, or `PVS1`.

### Phase 4: ClinVar-Derived PS1/PM5

The ClinVar-derived PS1/PM5 phase added conservative comparator-based evidence
generation for `PS1` and `PM5`. It uses ClinVar P/LP records only as comparator
records and independently checks protein change, nucleotide distinction,
transcript/protein match, condition match, germline applicability, assertion
quality, conflict status, provenance, and context consistency before emitting
applied evidence.

This phase formalized that ClinVar assertions do not become PP5/BP6 evidence.
Low-quality, conflicting, somatic-only, same-variant, condition-mismatched, or
context-mismatched comparators remain candidate-only or blocked.

### Phase 5: Manual Reviewed Evidence

The manual reviewed evidence phase added the explicit curator-controlled path
for applying ACMG evidence that cannot be safely generated automatically.
Records with `evidence_status=reviewed_applied` are strictly validated,
preserve curator rationale, review date, citation or provenance, and audit
trail, and are converted into normal `EvidenceItem` records upstream of the
existing combiner.

This phase enables curator-reviewed application of criteria such as `PS3`,
`BS3`, `PS2`, `PM6`, `PP1`, `PS4`, `PP4`, and `PM3` without allowing silent
promotion from candidate or suggested evidence. `reviewed_rejected` and
`needs_more_info` records remain review notes and are not counted.

### Phase 6: Literature Suggested to Reviewed Drafts

The literature-to-reviewed phase added a safe draft workflow from
`suggested_evidence` to manual `reviewed_evidence` templates. Drafts default to
`needs_more_info`, retain PMID/DOI/citation/extracted-claim provenance and
review questions, and require curator edits before any record can become
`reviewed_applied`.

This phase closes the current review loop without changing the combiner:
literature suggestions remain candidate-only by default, and only explicit
reviewed evidence can be supplied to classification.

### Phase 7: ClinGen ERepo Integration Validation

The ClinGen Evidence Repository phase validated ERepo as an external curated
source integration that stays inside the review-note and reviewed-draft safety
model. The integration surfaces gene-level VCEP activity signals, exact variant
match review notes, supporting summaries, citations, provenance, and
reviewed-evidence draft templates.

This phase did not add automatic applied evidence. ERepo exact variant matches
are review notes, ERepo supporting summaries become reviewed-evidence drafts,
and drafts require explicit curator action through the existing
`reviewed_applied` workflow before any criterion can enter classification. The
classification combiner remains unchanged.

### Phase 8: VCEP Signal / Override Framework

The VCEP signal/override phase implemented and validated the lightweight local
profile framework for versioned ClinGen/VCEP rule knowledge. It supports
gene-level VCEP profile signals, approved profile overrides,
draft/provisional signal-only profiles, deprecated limitation-only profiles,
profile conflict blocking, report provenance, and per-record
`vcep_profile_summary` output for batch and annotated-batch workflows.

This phase did not add full VCEP reasoning or automatic classification.
Signals alone do not change classification, approved overrides cannot bypass
generator safety gates, disabled criteria become candidate/review-note evidence
instead of silent deletions, and the ACMG classification combiner remains
unchanged.

### Phase 9: Real Provider Validation

The real provider validation phase validated the current ClinVar, gnomAD,
MANE/transcript, and ClinGen ERepo provider surfaces without making online
providers default behavior.

Completed validation includes:

- ClinVar real provider validation.
- gnomAD local snapshot validation.
- MANE transcript validation.
- Real resolution provider snapshot validation.
- ClinGen ERepo validation.

This phase confirmed the provider boundary: local fixtures or local snapshots
are the primary validation path, optional online behavior remains disabled by
default, provider cache/provenance/limitations are visible, provider failures
degrade to limitations, and no provider directly changes classification.

ClinVar can provide review notes and comparator facts for PS1/PM5, but not
direct PP5/BP6 or classification. gnomAD/local population snapshots provide
frequency facts that must pass through population rules and thresholds. MANE
and transcript metadata provide transcript/NMD/context review support but do
not apply PVS1 or other criteria. Resolution provider snapshots provide
descriptive transcript, protein, coordinate, exon, and NMD facts only. ERepo
provides exact-match review notes, gene-level VCEP activity signals, supporting
summaries, citations, and reviewed-evidence drafts, but not automatic applied
evidence.

### Phase 10: Benchmark Phase C Expansion

The benchmark Phase C expansion is complete. The current curated benchmark now
contains 100 offline SNV/small-indel cases with version
`offline-curated-v4-phase-c`.

Phase C kept the benchmark fully offline and provider fixture-backed. It
expanded `data/benchmark_provider_fixtures/` with local annotation and
transcript metadata fixtures in addition to population, ClinVar,
computational, literature, ClinGen ERepo, and VCEP profile fixtures.

Current benchmark coverage includes `PVS1`, `BA1`, `BS1`, `PM2_Supporting`,
`PP3`, `BP4`, `PS1`, `PM5`, manual reviewed evidence, literature draft
workflow boundaries, ClinGen ERepo review notes, VCEP signal/override behavior,
provider limitation cases, transcript/MANE validation, and strict
candidate/applied separation. The standalone real resolution provider
validation suite now covers local snapshot-backed transcript, protein,
coordinate, exon, and NMD resolution boundaries.

The latest full regression baseline after the v0.3.0 release review is
`626 passed, 1 skipped`.
The classification combiner remained unchanged.

### Phase 11: Variant Resolution Framework

The Variant Resolution Framework is implemented as an offline descriptive layer
between normalization and evidence generation. It resolves local
fixture-backed transcript, protein consequence, coordinate, exon, and NMD
context for supported HGVS c. inputs, including the BRCA1
`NM_007294.4:c.68_69delAG` fixture.

This phase preserves both `normalized_variant` and `resolved_variant` in
pipeline output and records the full `variant_resolution` payload in
`step_results["resolve_variant"]`. Existing generators may consume the richer
variant/context objects, but the resolution layer itself does not create ACMG
evidence, does not apply PVS1, and does not modify the combiner.

CLI and MCP now expose `resolve_variant` / `vpr resolve` for resolution-only
workflows. Reports include a Variant Resolution Summary with explicit wording
that the section is descriptive context only.

### Phase 12: Real Resolution Provider Validation

Real resolution provider validation is complete for the current offline
resolution surface. The local snapshot at
`data/transcript_resolution/real_resolution_provider_validation.jsonl` validates
HGVS c. to transcript, protein consequence, coordinate, exon, and NMD context
for BRCA1, CFTR, GJB2, DMD, PAH, and TP53, with BRCA2 retained as a
missing-mapping limitation case.

The validation adds resolution-specific review flags for build, transcript
accession, and transcript-version mismatches. Provider failures and missing
mappings remain limitations, resolution does not create evidence items, and the
classification combiner remains unchanged.

### Phase 13: Natural Language Input

Natural Language Input is implemented as a wrapper around the existing
normalization, resolution, rating, and reporting workflows. The parser supports
explicit natural-language/HGVS-like text extraction through `parse_variant_text`,
`rate_variant_from_text`, MCP tools, and CLI `vpr rate-text`.

This phase did not add ACMG rules or change classification logic. Parsed fields
remain normal workflow inputs, missing fields and ambiguities remain visible for
review, optional AI-assisted context is opt-in and candidate-only, and the ACMG
classification combiner remains unchanged.

## Current Complete Interpretation Workflow

```text
variant input
  -> optional natural-language parsing
  -> normalization / variant resolution / annotation / context consistency
  -> automatic applied evidence generation
  -> candidate/suggested evidence
  -> manual reviewed evidence
  -> combiner
  -> report
```

## Highest Priority Current Tasks

### 1. Selected Real-World Case Validation

Goal: validate selected real-world SNV/small-indel cases end to end using the
completed provider-validation posture: local fixtures/snapshots where possible,
optional online disabled by default, provenance visible, provider failures
converted to limitations, and no direct provider-driven classification.

Why it matters: curated benchmarks catch known rule regressions, but selected
real-world cases test realistic combinations of provider gaps, transcript
mismatch, population quality, ClinVar comparator ambiguity, and ERepo review
context.

Architecture impact: should focus on case data, expected outputs, provenance
review, report examples, and documentation. Business logic and the combiner
should remain stable unless a clearly scoped defect is found.

Safety risks: treating external assertions as truth, treating population
provider misses as absence, overusing transcript metadata to justify PVS1, and
weakening candidate/applied separation.

Expected deliverables: selected case set, per-case rationale, expected
applied/candidate/review-note evidence, expected limitations, provider
provenance review, and report examples.

Release gate expectations: no default network dependency, no direct provider
classification, no combiner change, and explicit limitations for unresolved
provider or context gaps.

### 2. Selected Real VCEP Profile Pilot

Goal: pilot one carefully selected real VCEP profile behind explicit selection,
now that toy profile validation and real provider validation are complete.

Why it matters: disease-specific profiles are the path from generic ACMG
support toward realistic internal interpretation workflows, but they require
validated rules, versioning, and disease-specific review.

Architecture impact: likely touches profile configuration, threshold
selection, evidence generator inputs, report provenance, documentation, and
profile-specific benchmarks.

Safety risks: silent profile activation, use with the wrong gene/disease,
incomplete inheritance or phenotype context, and overconfident classification
from profile-specific assumptions.

Expected deliverables: one narrow real VCEP profile pilot, explicit activation,
profile-version provenance, mismatch blocks, profile-off/profile-on report
examples, and a clear statement of what the pilot does not automate.

Release gate expectations: design approval, benchmark pass, no default clinical
profile activation, no combiner change without explicit review, and clear
profile limitations.

### 3. Optional Online Smoke Gates

Goal: add or standardize optional online smoke gates for provider reachability
and parser resilience without making network access part of default CI.

Why it matters: real online providers can drift. Optional smoke gates can catch
breaking endpoint or parser changes while preserving the current offline
validation baseline.

Architecture impact: should focus on gated smoke tests, provider provenance,
cache behavior, timeout/failure-to-limitation behavior, and documentation.

Safety risks: online smoke must not be treated as clinical validation, must not
introduce default network dependencies, and must not allow live provider
assertions to bypass local safety gates.

Expected deliverables: explicitly gated smoke command(s), cache/provenance
assertions, failure-to-limitation checks, and documentation that default CI
remains offline.

Release gate expectations: skipped by default, opt-in only, no combiner change,
and no direct provider-driven classification.

## Tasks Not Appropriate For The Current Stage

The following tasks should not be implemented in the current beta-stage roadmap
unless the project explicitly enters a validated clinical-development phase with
new data, governance, and review resources:

- CNV/SV interpretation, including DMD complex SV workflows. These require new
  variant models, interval/breakpoint normalization, dosage or mechanism
  evidence, and separate validation.
- Repeat expansion workflows. These require disease-specific repeat units,
  thresholds, inheritance context, and specialized reporting.
- Mitochondrial interpretation. This requires heteroplasmy, tissue context,
  mitochondrial-specific rules, and specialized evidence models.
- Methylation evidence. This requires assay-specific validation and disease
  context not present in the current SNV/small-indel pipeline.
- Automatic PS3/BS3 from literature or predictors. Functional evidence requires
  validated assays and manual review; computational prediction is not
  functional evidence.
- Automatic PS2/PM6/PP1/PS4/PP4/PM3 from literature or curated-source notes.
  These require trio/family/cohort evidence, parentage, segregation counts,
  phenotype specificity, trans/phasing context, deduplication, and qualified
  human review.
- Fully automated disease-specific VCEP interpretation. VCEP profiles require
  explicit profile versioning, validation, and disease-specific review.
- Clinical sign-out. The current system is a review-support and proposal tool,
  not a final reporting authority.

Tasks involving trio/family/cohort evidence, wet-lab functional assays, RNA
validation, or disease-specific clinical rules should remain candidate-only or
design-only until real validation data and review governance exist.
