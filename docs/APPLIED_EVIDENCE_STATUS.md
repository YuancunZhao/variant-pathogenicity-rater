# Applied Evidence Status

This document is the current applied evidence generation status review for
Variant Pathogenicity Rater. It summarizes which ACMG criteria can currently be
emitted as applied `EvidenceItem` records, which outputs remain candidate-only,
which criteria are not implemented for automatic application, and which work
should be prioritized next.

The classification combiner remains unchanged. It combines supplied evidence
items and does not trigger evidence. Candidate-only and review-note evidence
must remain visible for review but excluded from classification.

## Current Benchmark Validation

Benchmark Phase C is complete and is the current applied-evidence regression
baseline:

- 100 offline curated SNV/small-indel cases.
- Benchmark version `offline-curated-v4-phase-c`.
- Provider fixture-backed, including population, ClinVar, computational,
  literature, ClinGen ERepo, VCEP profile, annotation, and transcript metadata
  fixtures.
- Latest full regression status after General Literature Engine integration
  review: `641 passed, 1 skipped`.

The benchmark covers applied and candidate boundaries for `PVS1`, `BA1`,
`BS1`, `PM2_Supporting`, `PP3`, `BP4`, `PS1`, `PM5`, manual reviewed evidence,
literature draft workflows, the General Literature Search and Summary Engine,
ClinGen ERepo review notes, VCEP signal/override behavior, provider
limitations, transcript/MANE validation, and strict candidate/applied
separation. It remains a safety regression set rather than a clinical truth
set.

## Implemented Applied Evidence

Current automatic applied evidence generation supports:

- `PVS1`
- `BA1`
- `BS1`
- `PM2_Supporting`
- `PP3`
- `BP4`
- `PS1`
- `PM5`

All generated applied evidence requires qualified human review and must retain
provenance, decision paths, limitations, and safety-gate results.

Current applied evidence depends on validated provider facts only through the
appropriate rule layer:

- `PVS1` depends on transcript relevance, NMD/terminal-exon or splice context,
  consequence support, LoF disease mechanism, inheritance/context consistency,
  and reviewable limitations. MANE/transcript providers can support context
  review but cannot apply PVS1 directly.
- `BA1`, `BS1`, and `PM2_Supporting` depend on population provider facts and
  configured thresholds. gnomAD/local population snapshots supply AF/AC/AN/FAF,
  ancestry, build, quality, and provenance; `population_rules` decides whether
  evidence can be applied.
- `PP3` and `BP4` depend on computational provider consensus, appropriate
  variant context, transcript/build matching, source quality, and conflict
  checks. A single predictor or conflicting predictors are insufficient.
- `PS1` and `PM5` depend on ClinVar comparator facts plus protein/transcript
  matching, nucleotide distinction, condition match, germline applicability,
  assertion quality, conflict checks, and provenance. ClinVar assertions are
  not copied directly into classification.

The 74 real provider pipeline adds opt-in online ClinVar, gnomAD, Ensembl VEP,
PubMed, and LitVar adapters. These providers supply records and provenance
only. They do not create applied evidence and do not modify the classification
combiner. Online gnomAD and VEP facts still pass through the existing
population and computational evaluators; ClinVar and literature remain
review-note/candidate-only unless a curator later supplies valid
`reviewed_applied` evidence.

No provider directly changes classification. Providers supply facts, review
notes, or drafts; applied evidence enters classification only through validated
generators or explicit manual `reviewed_applied` evidence.

Manual reviewed evidence is also supported as an explicit curator-supplied
workflow. It is not automatic evidence generation: only records with
`evidence_status=reviewed_applied` are converted into applied `EvidenceItem`
objects, while `reviewed_rejected` and `needs_more_info` records remain
review-note evidence.

The implemented human-reviewed pathway is:

```text
candidate/suggested evidence
  -> reviewed-evidence draft
  -> explicit curator decision
  -> reviewed_applied, reviewed_rejected, or needs_more_info
  -> curator-applied evidence only when reviewed_applied is valid
```

This pathway is shared by direct reviewed evidence intake, literature
suggestions, and ClinGen ERepo supporting summaries. Literature and ERepo draft
generation reduces transcription work for curators; it does not apply evidence.

The General Literature Search and Summary Engine extends the candidate
literature workflow but does not expand the applied-evidence list.
`search_and_summarize_literature` supports query planning, local/offline
caller-supplied literature records, duplicate collapse, criterion-specific
summaries for `PS3`/`BS3`, `PS2`/`PM6`, `PP1`, `PS4`, `PM3`, `PP4`,
`PS1`/`PM5`, `PM1`, and `PVS1` mechanism support, and reviewed-evidence draft
output. `suggested_strength` is reviewer guidance only; literature-derived
evidence-like outputs remain `candidate_only=true`, `applied=false`, and
`strength=none`.

The current applied evidence surface therefore includes automatic generated
`PVS1`, `BA1`, `BS1`, `PM2_Supporting`, `PP3`, `BP4`, `PS1`, and `PM5`, plus
curator-reviewed applied evidence such as `PS3`, `BS3`, `PS2`, `PM6`, `PP1`,
`PS4`, `PP4`, and `PM3` when, and only when, explicitly supplied as
`reviewed_applied`.

The VCEP signal/override framework is implemented and validated, but it does
not expand the automatic applied-evidence list. VCEP gene-level signals,
draft/provisional profiles, deprecated profiles, conflicts, and unsupported
profile contexts remain review context, limitations, or candidate/review-note
material. Approved profile overrides can only adjust the allowed safe generator
parameters or downgrade/disable generated criteria before classification.

## Evidence-Specific Status

### PVS1

`PVS1` is generated by a conservative SNV/small-indel loss-of-function decision
tree.

Applied PVS1 requires:

- Supported LoF consequence in scope for the current implementation.
- Confirmed LoF disease mechanism for the gene-disease context.
- Complete gene, disease, and inheritance context.
- Relevant transcript context.
- NMD, terminal-exon, or splice path sufficient for the selected strength.
- No blocking context consistency conflict.
- No in-frame rescue or preserved-reading-frame concern.

Safety gates keep PVS1 conservative. Consequence labels alone do not apply
PVS1. Start-loss, stop-loss, uncertain splice, unknown NMD, transcript mismatch,
missing disease context, unconfirmed LoF mechanism, context conflict, or rescue
risk keeps output candidate-only, blocked, or not applicable.

### BA1, BS1, and PM2_Supporting

Population evidence is generated from population allele-frequency records and
configured thresholds.

Applied `BA1` and `BS1` require:

- Usable AF that meets the configured BA1 or BS1 threshold.
- Disease-specific threshold context.
- Penetrance, prevalence, inheritance, disease, and population context.
- Matched population and ancestry assumptions.
- Adequate allele number and coverage.
- Matching genome build.
- Source version and provenance.
- No low-confidence provider flag, founder-population warning, or context
  consistency conflict.

Applied `PM2_Supporting` requires a usable matched record showing zero or very
low AF at or below the PM2 threshold under the same quality gates. A provider
miss, no local record, malformed record, or unusable AF is not evidence of
absence and does not trigger PM2.

If the AF points toward BA1, BS1, or PM2_Supporting but any safety gate fails,
the generator emits candidate-only evidence with `strength=none`,
`candidate_only=true`, and `applied=false`.

### PP3 and BP4

Computational evidence is generated from calibrated predictor consensus and is
capped at supporting strength.

Applied `PP3` requires:

- At least the configured number of calibrated predictors supporting a
  deleterious effect.
- No benign/no-effect predictor conflict.
- Variant consequence appropriate for the predictor group.
- Source quality, transcript match, genome-build match, and context consistency
  gates passing.
- No same-mechanism double counting with applied PVS1.

Applied `BP4` requires:

- At least the configured number of calibrated predictors supporting benign or
  no effect.
- No pathogenic predictor conflict.
- Variant consequence appropriate for benign computational use.
- No splice/high-impact context that blocks benign computational evidence.

Predictor conflict, insufficient independent support, source-quality failure,
transcript or genome-build mismatch, consequence mismatch, or context conflict
keeps output candidate-only or limitation-only. SpliceAI and similar predictors
are computational support only; they are not RNA validation, functional assay
evidence, `PS3`, `BS3`, or `PVS1`.

### PS1 and PM5

ClinVar-derived PS1/PM5 generation is a comparator workflow. ClinVar is used as
a source of previously asserted pathogenic/likely pathogenic comparator
variants, not as direct PP5/BP6 evidence.

Applied `PS1` requires:

- Query and comparator have parseable protein consequences.
- Same amino acid change.
- Confirmed different nucleotide or genomic change.
- Comparator is not the same variant.
- Transcript or protein accession matches.
- Disease/condition matches.
- ClinVar comparator is high-quality, germline applicable, P/LP, and
  non-conflicting.
- No blocking context consistency conflict.

Applied `PM5` requires:

- Query and comparator are parseable missense changes.
- Same reference amino acid and residue position.
- Different alternate amino acid.
- Transcript or protein accession matches.
- Disease/condition matches.
- ClinVar comparator is high-quality, germline applicable, P/LP, and
  non-conflicting.
- No blocking context consistency conflict.

Missing or unparseable protein consequence, unresolved nucleotide difference,
low-quality ClinVar assertion, transcript/protein uncertainty, or provider gaps
keep output candidate-only. ClinVar conflict, somatic-only assertion,
condition mismatch, same-variant comparison, or context conflict blocks applied
PS1/PM5. ClinVar assertions never become automatic PP5/BP6.

## Candidate-Only Fallbacks

The system intentionally preserves candidate and review-note outputs for
review. These outputs may guide a reviewer but must not alter classification.

Candidate-only fallback occurs when:

- Evidence appears directionally relevant but one or more safety gates fail.
- Provider data is incomplete, low confidence, stale, or missing provenance.
- Disease, inheritance, ancestry, transcript, genome-build, or condition
  context is missing or mismatched.
- Predictor or comparator data conflicts.
- Evidence requires family, cohort, functional, literature, or VCEP-specific
  judgment that is not implemented as automatic applied evidence.

Candidate-only evidence uses `strength=none`, `candidate_only=true`, and
`applied=false` where represented as an `EvidenceItem`.

ClinGen Evidence Repository matches are part of this candidate/review-note
surface. Exact ERepo matches, VCEP criteria summaries, and gene-level VCEP
activity signals do not automatically create applied ACMG evidence. ERepo
reviewed-evidence drafts default to `needs_more_info` and require the existing
manual reviewed evidence workflow before any evidence can be applied.

External curated-source integration currently includes ClinVar and ClinGen
Evidence Repository. ClinVar provides review notes and conservative PS1/PM5
comparator context. ERepo provides gene-level VCEP signal, exact variant match
review notes, supporting summaries, citations, provenance, and reviewed-evidence
drafts. Neither source automatically classifies a variant.

## Not Implemented For Automatic Applied Evidence

The following are not implemented as automatic applied evidence:

- `PS2` / `PM6`: requires trio/de novo evidence, parentage, phenotype
  consistency, maternity/paternity confirmation, and manual review.
- `PP1`: requires segregation counts, family structure, phenotype match,
  phasing, independence, and manual review.
- `PS4`: requires case-control or enrichment evidence, cohort definition,
  statistical support, ancestry matching, duplicate-case control, and manual
  review.
- `PS3` / `BS3` automatic applied: functional evidence requires validated assay
  relevance and expert review. Computational predictors, including SpliceAI, do
  not satisfy PS3/BS3.
- `PM3`: requires in-trans evidence, phase confidence, affected status,
  zygosity, allelic series context, and manual review.
- `PP4`: requires highly specific phenotype context and expert disease review.
- BA1/BS1 disease-specific refinements beyond the current configurable
  threshold gates require explicit VCEP/profile provenance and approved profile
  override activation before use.
- VCEP-specific full reasoning is not implemented. No VCEP profile is activated
  by default. The lightweight VCEP signal/override framework supports local,
  explicitly enabled gene-level signals and limited safe generator-parameter
  overrides; it is not a full VCEP reasoning engine and does not change the
  combiner.

Literature and ClinVar review-note workflows may surface suggestions related to
these criteria, but suggestions remain candidate-only unless the manual
reviewed evidence workflow explicitly supplies applied evidence under strict
validation.

The General Literature Search and Summary Engine may summarize these criteria
from caller-supplied or offline/local literature records, but it does not
automatically infer applied criteria. Duplicate publications, families, and
cohorts are collapsed before summaries; variant and disease mismatches become
blocking flags; abstract-only evidence becomes a limitation; low-confidence
extraction becomes a review flag; reviewed drafts default to
`needs_more_info`.

The current software can count `PS3`/`BS3`, `PS2`/`PM6`, `PP1`, `PS4`, `PP4`,
and `PM3` only through explicit manual reviewed evidence. It does not
automatically infer these criteria from literature, ClinVar notes,
computational predictions, family text, case counts, phenotype descriptions, or
PM3-like trans observations.

## Remaining Risks

- Disease-specific thresholds and VCEP profiles are still limited; generic
  thresholds can be inappropriate for real clinical interpretation if not
  reviewed.
- Literature, segregation, de novo, functional, case-count, phenotype, and PM3
  evidence remain suggestion/review workflows rather than applied automation.
  The general literature engine improves search/summarization and draft
  preparation, not automatic evidence application.
- Condition and phenotype matching are conservative and do not yet use a full
  ontology/profile system.
- Provider provenance and source snapshots remain essential; missing provenance
  should continue to block or downgrade evidence.
- Benchmark coverage is safety-oriented and still small relative to the ACMG
  surface, even after Phase C expansion to 100 cases.
- All generated evidence remains machine proposal material and requires
  qualified human review.
- VCEP signal-only output, approved overrides, and disabled-criterion
  downgrades must continue to preserve report visibility and profile
  provenance.

## Recommended Next Task

The recommended next task is selected real-world case validation.

The applied evidence loop, lightweight VCEP signal/override framework, current
real provider validation surface, benchmark Phase C baseline, Chinese report
output, offline variant resolution, and General Literature Search and Summary
Engine are complete enough for controlled internal validation. Local
fixtures/snapshots remain the primary validation path, optional online behavior
is disabled by default, provenance/cache/limitations are visible, failures
degrade to limitations, candidate/review-note evidence stays outside
classification, and no provider directly changes classification.

The next priorities are:

- Selected real-world case validation.
- Online PubMed/LitVar adapter pilot for the literature engine, behind explicit
  opt-in and local/offline validation.
- Selected real VCEP profile pilot.
- CNV/SV framework planning as design-only work.

Current known gaps remain selected real-world case validation, online
PubMed/LitVar adapter implementation, selected real VCEP profile pilot, larger
real-world hospital annotation validation, and CNV/SV support.
