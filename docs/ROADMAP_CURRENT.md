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

## Current Complete Interpretation Workflow

```text
variant input
  -> normalization / annotation / context consistency
  -> automatic applied evidence generation
  -> candidate/suggested evidence
  -> manual reviewed evidence
  -> combiner
  -> report
```

## Highest Priority Current Tasks

### 1. Toy Profile Validation

Goal: validate the completed VCEP signal/override framework with intentionally
small toy profiles that exercise profile-off/profile-on behavior, approved
override provenance, draft/provisional signal-only handling, deprecated
limitation-only handling, profile conflict blocking, and per-record batch
summaries.

Why it matters: the framework plumbing is now implemented, but toy profiles are
the safest way to prove each boundary before introducing real VCEP guidance.

Architecture impact: should focus on validation fixtures, benchmark cases,
report examples, and documentation. Business logic, tests outside the intended
validation surface, and the combiner should remain stable.

Safety risks: overinterpreting toy profiles as clinical guidance, missing
candidate/applied leakage, and losing provenance in batch or annotated-batch
outputs.

Expected deliverables: toy profile fixture set, profile-off/profile-on
comparison cases, report examples, batch/annotated-batch examples, and
documented safety expectations.

Release gate expectations: no default profile activation, no combiner change,
candidate-only leakage checks, report provenance checks, and batch
`vcep_profile_summary` checks.

### 2. Real Provider Validation: ClinVar / gnomAD / MANE / ERepo Online

Goal: validate provider behavior against real ClinVar, gnomAD, MANE, and
ClinGen ERepo online data using opt-in or local-fixture workflows with source
versions, provenance, and failure-to-limitation behavior.

Why it matters: the current loop is useful, but real provider validation is
needed before broader internal use. Concordance with external assertions is not
clinical correctness, so validation must focus on provenance, context matching,
and safe degradation.

Architecture impact: expected changes should focus on provider fixtures,
validation scripts or smoke tests, documentation, provenance checks, and report
review. Online behavior must remain explicitly gated.

Safety risks: direct ClinVar assertion reuse, treating provider misses as
absence, hiding MANE/transcript mismatch, and weakening candidate/applied
separation under real-data pressure.

Expected deliverables: documented validation protocol, local snapshots or
fixtures where possible, ClinVar/gnomAD/MANE/ERepo provenance checks, mismatch
examples, and review of failure wording.

Release gate expectations: no network dependency in default tests, no candidate
leakage, source-version documentation, opt-in ERepo online checks,
failure-to-limitation checks, and combiner unchanged.

### 3. Benchmark Expansion

Goal: expand the curated benchmark beyond the current beta-sized set while
keeping it offline, auditable, and safety-focused.

Why it matters: the current 21-case benchmark is useful but small. More cases
are needed to catch regressions in PVS1 restraint, population thresholds,
computational conflicts, ClinVar conflict handling, manual reviewed evidence,
literature drafts, and candidate evidence separation.

Architecture impact: should primarily touch data fixtures and tests, not
runtime business logic. This is a validation/hardening task rather than feature
implementation.

Safety risks: benchmark expected classifications must not be used to justify
weakening safety logic. Uncertain cases should allow conservative outcomes
rather than forcing overconfident labels.

Expected deliverables: expanded curated case file, rationale per case, expected
applied/candidate/reviewed evidence, expected limitations/review flags, and
updated benchmark documentation.

Release gate expectations: benchmark pass, full pytest pass, no combiner
relaxation, and clear statement that the benchmark is not a clinical truth set.

### 4. Chinese Report Template

Goal: provide a Chinese-language report template that preserves the same safety
wording, applied/candidate separation, reviewed-evidence labeling, provenance,
limitations, and review-required posture as the existing reports.

Why it matters: report usability improves when reviewers can read safety
language and evidence summaries in the language of their workflow.

Architecture impact: expected changes should be in reporting templates,
formatting, localization wording, and report tests. It must not change
classification behavior.

Safety risks: translated wording must not imply clinical sign-out, certainty,
or automatic evidence application. VUS caution and human review requirements
must remain explicit.

Expected deliverables: Chinese Markdown/report output, terminology glossary,
report tests, and documentation showing parity with English safety sections.

Release gate expectations: report wording safety review by a qualified reader,
pytest pass, smoke report generation, and no changes to evidence logic or the
combiner.

### 5. Selected Real VCEP Profile Pilot

Goal: after toy profile validation and real provider validation, pilot one
carefully selected real VCEP profile behind explicit selection.

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
