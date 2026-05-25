# v0.2.0 Beta Gap Analysis

Review date: 2026-05-25
Current release baseline: v0.2.0-alpha2
Target: v0.2.0-beta
Scope: gap analysis only; no business-code, version, or provider behavior changes

## Summary

v0.2.0-alpha2 has moved Variant Pathogenicity Rater beyond the original internal
prototype: it now has CLI and MCP surfaces, single and batch rating paths,
annotated batch ingestion, normalization, transcript selection, provider-mode
controls, and conservative safety boundaries around ClinVar, population,
SpliceAI-style computational evidence, and literature candidate evidence.

The remaining beta gap is not a single missing feature. It is controlled
hardening: noisy real-world inputs, context consistency, annotation quality
checks, larger safety regression sets, provider validation, and report usability.
The beta should remain an internal controlled-evaluation release, not a clinical
validation statement.

Current known gate from alpha2 release review:

- Full test suite: 244 passed.
- Benchmark dataset: 21 curated SNV/small-indel cases.
- Real-data smoke dataset: 10 offline curated cases.
- Default provider posture: offline/mock; no network required.
- Safety posture: human review required for every result and report.

## 1. Current Capability Boundary

### Single Variant

Current state:

- `rate_variant` orchestrates normalization, provider retrieval, population
  rules, computational evidence, PVS1, candidate ClinVar/literature notes,
  classification combining, and report generation.
- Supported variant class remains SNV/small indel only.
- Normalization preserves unresolved fields and emits warnings rather than
  making unsafe coordinate or transcript assumptions.
- ClinVar and literature findings remain candidate/review-note evidence and do
  not directly apply PP5/BP6 or strong literature-derived criteria.
- PM2 remains intentionally conservative and capped at supporting strength.

Beta gap:

- Need stronger noisy input coverage for partially specified HGVS, VCF-like,
  transcript-version, genome-build, and gene-context edge cases.
- Need explicit context-consistency checks that can flag gene, transcript,
  disease, inheritance, and provider-record mismatches before users read the
  classification proposal as more coherent than the evidence supports.

### Batch

Current state:

- `vpr batch` and MCP batch workflows accept JSON, JSONL, CSV/TSV, and minimal
  VCF-like inputs.
- Per-record failures are preserved in `failed_records` and mirrored in results.
- Partial-failure behavior is configurable from CLI.
- Batch classification still routes through the same conservative single-variant
  pipeline.

Beta gap:

- Need better row-level summaries so a reviewer can immediately see counts by
  success, failed normalization, unsupported variant class, provider issue,
  review flag, and final classification.
- Need broader malformed-row and mixed-quality-input tests to prevent silent
  failure or hidden per-row warnings.

### Annotated Batch

Current state:

- `vpr annotated-batch` and MCP `rate_annotated_variants` accept VEP, ANNOVAR,
  `bcftools csq`, and generic annotation formats.
- Annotation provenance, normalization identity, transcript-selection summary,
  review flags, limitations, and failed-record details are preserved.
- Annotation does not directly generate ACMG evidence.

Beta gap:

- Need annotation quality checks that detect missing source metadata, missing or
  conflicting genome build, malformed transcript fields, inconsistent gene
  symbols, mismatched HGVS c./p. values, ambiguous consequences, and unsupported
  variant classes.
- Need explicit quality status in batch summaries and report output.

### Provider Modes

Current state:

- Default provider mode is offline/mock.
- Online ClinVar is opt-in only and candidate-only.
- Local-file provider behavior exists for smoke-style ClinVar and population
  fixtures.
- Population online, literature online, and computational online providers are
  not implemented for alpha2.

Beta gap:

- Need provider validation strategy across mock, local-file, and opt-in online
  ClinVar modes.
- Need local gnomAD snapshot validation before population-frequency behavior can
  be trusted beyond curated fixtures.
- Need online ClinVar field validation for identity, condition specificity,
  review status, variation identifiers, transcript/protein context, and
  submission conflicts.

### CLI and MCP

Current state:

- CLI commands include `rate`, `batch`, `annotated-batch`, and `check-env`.
- MCP tools include single, batch, and annotated-batch rating workflows with
  strict top-level schema validation and structured errors.
- Examples and documentation exist for CLI and MCP workflows.

Beta gap:

- Need beta-ready example validation across CLI and MCP, including noisy input,
  failed records, annotated batch, provider mode differences, and report output.
- Need report usability review so CLI/MCP consumers see review flags,
  limitations, candidate evidence, and failed records without digging through
  deeply nested JSON.

### Offline and Online Status

Current state:

- Offline/mock remains the default and the expected release-review posture.
- Existing tests and smoke workflows should not call live services.
- Online ClinVar is opt-in and must remain review-note only.

Beta gap:

- Need documented online-validation procedures that can be run separately from
  default offline tests.
- Need provider status reporting that makes clear whether a result came from
  mock, local snapshot, or online source, and whether a provider miss means
  "not found in this configured source" rather than population absence.

## 2. Beta P0 Must-Haves

### P0.1 Real-World Noisy Input Handling

Why it is P0:

- Beta users will provide partially structured, inconsistent, or caller-specific
  inputs. Unsafe normalization assumptions are a direct overcalling risk.

Required beta behavior:

- Preserve invalid or ambiguous fields with structured warnings.
- Reject out-of-scope CNV/SV-like records with structured errors.
- Distinguish malformed input, unsupported input, unresolved normalization, and
  provider no-record states.
- Add regression cases for common noisy forms: missing transcript version,
  cDNA-only input, protein-only context, incomplete VCF rows, build-uncertain
  records, multiallelic-looking records, inconsistent chrom/pos/ref/alt, and
  mixed valid/invalid batch files.

### P0.2 Transcript/Gene/Disease Context Consistency

Why it is P0:

- A variant can appear coherent while the transcript, gene, protein effect,
  disease, inheritance, and provider assertion describe different contexts.

Required beta behavior:

- Surface mismatches between user-supplied gene, annotation gene, selected
  transcript, HGVS transcript, ClinVar transcript/protein context, and disease
  context.
- Keep mismatch checks review-facing rather than silently changing evidence.
- Flag condition and inheritance mismatches before a reader reaches the final
  classification proposal.
- Add transcript edge cases: MANE/canonical disagreement, transcript version
  differences, input transcript absent from annotation, multiple consequences,
  protein-effect mismatch, and gene symbol alias ambiguity.

### P0.3 Annotation Quality Checks

Why it is P0:

- Annotated batch is now a real-world workflow. Without quality checks, a
  successful parse can look safer than it is.

Required beta behavior:

- Add row-level quality status for annotation records.
- Detect missing source version, missing genome build, missing transcript,
  unsupported consequence, ambiguous consequence, gene/HGVS conflict, and
  partial coordinate identity.
- Ensure warnings propagate into batch output and reports.
- Keep annotation quality checks separate from ACMG evidence application.

### P0.4 Benchmark Expansion Strategy

Why it is P0:

- The 21-case benchmark is useful for alpha regression but too small for beta
  safety confidence.

Required beta target:

- Expand benchmark to at least 100 curated SNV/small-indel cases.
- Preserve balanced five-tier coverage: benign, likely benign, VUS, likely
  pathogenic, and pathogenic.
- Add negative controls for sparse evidence, conflicting evidence, transcript
  mismatch, condition mismatch, population ancestry mismatch, candidate-only
  ClinVar/literature, PVS1 edge cases, and PM2+PP3 overcalling prevention.
- Track expected applied evidence, expected candidate evidence, expected review
  flags, and rationale for every case.

### P0.5 Real-Data Smoke Expansion Strategy

Why it is P0:

- The 10-case smoke set catches important regressions but does not yet represent
  enough real-world input variety.

Required beta target:

- Expand real-data smoke to at least 50 cases.
- Keep the suite offline by default.
- Include HGVS, VCF-like, local annotation, ClinVar-like fixture, and
  population-snapshot-like fixture examples.
- Add cases for no-record semantics, source mismatch, build mismatch, malformed
  annotations, transcript mismatch, ancestry-specific frequency, and candidate
  evidence separation.

### P0.6 Provider Validation Strategy

Why it is P0:

- Provider mode differences can change what evidence appears available, even
  when the classification combiner stays conservative.

Required beta behavior:

- Define validation matrices for mock, local-file, and opt-in online ClinVar
  paths.
- Validate no-record semantics: provider miss must not mean database absence.
- Validate source provenance: source name, query, retrieval time, snapshot
  version, parser version, genome build, and provider mode.
- Validate online ClinVar separately from default tests and keep it
  candidate-only.

### P0.7 Report Usability

Why it is P0:

- A conservative engine can still be misused if reports make warnings,
  limitations, or candidate-only evidence hard to see.

Required beta behavior:

- Make human-review-required language prominent in JSON, Markdown, and plain
  text paths.
- Make candidate/review-note evidence visually and structurally separate from
  applied ACMG criteria.
- Summarize per-record batch failures and high-severity review flags before
  detailed evidence.
- Include provider mode, source status, transcript context, disease context,
  limitations, and unresolved fields in reviewer-facing sections.

## 3. P1 / P2

### P1: Chinese Report Localization

Goal:

- Add Chinese report rendering for reviewer-facing sections, warnings, safety
  language, evidence summaries, and batch summaries.

Constraints:

- Keep ACMG criterion codes, source identifiers, variant names, classification
  values, and evidence IDs unambiguous.
- Preserve explicit language that the report is not direct clinical sign-out.

### P1: Local gnomAD Snapshot Validation

Goal:

- Validate local population snapshot parsing, allele-count/frequency mapping,
  ancestry labels, genome build metadata, and no-record behavior.

Constraints:

- Do not treat local snapshot absence as population absence.
- Keep ancestry coverage limitations visible in evidence and reports.

### P1: ClinVar Online Field Validation

Goal:

- Validate opt-in online ClinVar responses against real-world field variation.

Fields to validate:

- Variation ID, allele identity, HGVS names, gene symbol, condition, clinical
  significance, review status, submitter conflict, transcript/protein context,
  and retrieval provenance.

Constraints:

- ClinVar remains candidate/review-note only.
- No automatic PP5/BP6.

### P2: PubMed/LitVar Read-Only Candidate Extraction

Goal:

- Add read-only candidate extraction from PubMed/LitVar-style metadata, where
  available.

Constraints:

- Extracted literature signals remain candidate-only.
- No automatic PS3/BS3, PS2/PM6, PP1, PS4, or PP4.
- Require PMID or stable source identifier, query text, retrieval time, and
  candidate rationale.

### P2: Batch Output Summarization

Goal:

- Improve batch output readability without hiding per-record details.

Suggested summary fields:

- Total records, successful records, failed records, unsupported records,
  records with review flags, records with limitations, classification counts,
  provider-mode counts, and top failure reasons.

## 4. Not Entering Beta

The following should remain outside v0.2.0-beta scope:

- CNV interpretation.
- SV interpretation.
- DMD complex structural variant handling.
- Automatic PS3/BS3 application from functional evidence.
- Automatic PP1, PS2, or PS4 application from segregation, de novo, or
  case-enrichment evidence.
- Direct clinical sign-out or workflows implying final diagnostic authorization.

These items need separate domain models, validation datasets, clinical
governance, and evidence-specific safety controls.

## 5. Risk Register

| Risk | Why It Matters | Beta Mitigation |
| --- | --- | --- |
| Pathogenic overcalling | Sparse, candidate-only, or mismatched evidence could be interpreted too strongly. | Keep candidate evidence separate, preserve conservative combiner behavior, expand overcalling regression tests, and require safety review. |
| Benign overcalling | Population frequency can be misapplied when ancestry, disease prevalence, penetrance, or snapshot quality is unclear. | Require threshold context, preserve ancestry coverage warnings, avoid treating provider miss as absence, and add ancestry-mismatch cases. |
| Transcript mismatch | User input, annotation records, ClinVar, and computational sources may refer to different transcripts or protein effects. | Add transcript consistency checks, report selected transcript and alternatives, and test transcript-version/protein mismatch cases. |
| Disease mismatch | ClinVar or literature assertions may describe a different condition or inheritance model. | Surface condition and inheritance conflicts, keep ClinVar/literature candidate-only, and require disease-context review flags. |
| Population ancestry mismatch | Frequency thresholds can be unsafe when population labels or coverage differ across snapshots. | Validate ancestry field mapping, show coverage limitations, and add ancestry-specific smoke and benchmark cases. |
| Annotation source inconsistency | Local annotation files may have stale versions, missing build metadata, or parser-specific field conventions. | Add annotation quality status, require source provenance, and propagate row-level limitations into reports. |
| Literature hallucination | Automated literature handling may infer evidence not present in abstracts or metadata. | Restrict to read-only candidate extraction with stable identifiers, query provenance, and no automatic ACMG application. |
| Batch silent failure | Multi-record workflows can hide malformed rows, skipped variants, or provider failures. | Preserve failed records, add batch summaries, test mixed-quality inputs, and keep per-record review flags visible. |
| Report misinterpretation | Users may treat machine proposals as final clinical assertions. | Make human review required prominent, separate applied and candidate evidence, and include limitations before final use. |

## 6. Proposed Beta Milestones

### beta-prep1: Noisy Input Hardening

Deliverables:

- Expanded malformed/noisy input fixtures for single, batch, and annotated batch.
- Structured warnings for ambiguous HGVS, VCF-like, transcript, build, and
  unsupported-class inputs.
- Regression tests confirming no silent row drops and no new overcalling.

Exit criteria:

- Full pytest suite passes.
- Mixed valid/invalid batch and annotation files preserve all records.
- Unsupported CNV/SV-like inputs produce structured errors.

### beta-prep2: Context Consistency Checks

Deliverables:

- Gene/transcript/disease/inheritance consistency checks.
- Transcript mismatch and protein-effect mismatch review flags.
- Report-visible context summary.

Exit criteria:

- Transcript and condition mismatch cases are visible in output.
- Context warnings do not automatically apply ACMG criteria.
- Human review remains required.

### beta-prep3: Benchmark/Smoke Expansion

Deliverables:

- Benchmark expansion from 21 to at least 100 cases.
- Real-data smoke expansion from 10 to at least 50 cases.
- Coverage notes for overcalling, benign overcalling, mismatch, provider, and
  candidate-evidence scenarios.

Exit criteria:

- Expanded benchmark passes.
- Expanded real-data smoke passes offline.
- No new overcalling behavior is accepted.

### beta-prep4: Report Usability Review

Deliverables:

- Batch summary improvements.
- Report review for JSON, Markdown, plain text, CLI, and MCP consumers.
- Optional Chinese localization scoped for review-facing report text.

Exit criteria:

- Review flags, limitations, provider mode, candidate evidence, and failed
  records are easy to find.
- CLI/MCP examples are validated.
- Reports clearly state that human review is required.

### Beta Release Review

Deliverables:

- Updated release readiness review.
- Updated known limitations.
- v0.2.0-beta release notes.
- Validated CLI and MCP examples.

Exit criteria:

- Full pytest suite passes.
- Benchmark and real-data smoke targets are met.
- Safety review passes.
- Documentation reflects beta behavior and remaining limits.

## 7. Definition of Done for Beta

v0.2.0-beta is done only when all of the following are true:

- Full pytest suite passes.
- Benchmark has at least 100 curated cases.
- Real-data smoke has at least 50 cases.
- No new overcalling behavior is introduced.
- Safety review passes.
- Documentation is complete for CLI, MCP, provider modes, known limitations,
  benchmark, real-data smoke, and reports.
- CLI examples are validated.
- MCP examples are validated.
- Human-review-required behavior remains present in every result and report.
- Candidate ClinVar, literature, and annotation-derived signals remain separate
  from applied ACMG criteria.

## 8. Suggested Next Task

Recommended first coding task after alpha2:

**Implement beta-prep1 noisy input hardening for annotated batch and batch
normalization paths.**

Suggested scope:

- Add a small structured "input quality" layer for parsed batch and annotation
  records.
- Detect and preserve warnings for missing genome build, missing transcript,
  incomplete HGVS, inconsistent coordinate identity, unsupported variant class,
  malformed allele fields, and conflicting gene/HGVS context.
- Propagate these warnings into per-record output, `failed_records`, and report
  limitations.
- Add tests for mixed valid/invalid JSONL, CSV/TSV, VCF-like, VEP, ANNOVAR, and
  generic annotation inputs.
- Confirm no ACMG business logic changes and no new evidence application.

Why this should be first:

- It is a P0 beta blocker.
- It reduces the largest practical risk introduced by real-world workflows.
- It is testable offline.
- It strengthens CLI, MCP, batch, annotated batch, and report behavior without
  expanding clinical scope.
- It creates the foundation for later context consistency checks and provider
  validation.
