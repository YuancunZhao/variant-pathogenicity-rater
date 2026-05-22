# v0.2.0 Development Plan

Planning date: 2026-05-22
Target release: v0.2.0
Base branch: `develop`
Scope: clinically safer beta for SNV/small-indel ACMG support

## Summary

v0.2.0 should move Variant Pathogenicity Rater from an internal prototype toward
a clinically safer beta. The release should improve compatibility with real
annotation data, strengthen evidence traceability, and keep all classifications
as machine-generated proposals that require qualified human review.

This plan does not expand the project beyond SNV/small-indel interpretation and
does not authorize autonomous clinical reporting.

## v0.2.0 Goals

- Move from the v0.1.0 internal prototype to a clinically safer beta suitable
  for broader controlled internal evaluation.
- Improve compatibility with real-world variant inputs, local annotation
  snapshots, transcript-specific records, and ClinVar responses.
- Make evidence traceability easier to audit from input normalization through
  provider retrieval, criterion assessment, classification, and report output.
- Preserve conservative safety behavior, including `human_review_required` on
  every result and report.
- Avoid new automatic evidence application when the underlying source cannot be
  interpreted safely and reproducibly.

## Recommended Feature Priorities

### P0: Annotation And Normalization Foundation

1. Local VEP/ANNOVAR annotation adapter
   - Add a provider-facing adapter for locally supplied VEP or ANNOVAR-style
     tabular outputs.
   - Normalize records into project evidence and annotation models with source,
     snapshot, genome build, transcript, parser version, and row-level
     provenance.
   - Treat malformed rows, build mismatches, missing transcript fields, and
     unsupported consequence terms as structured warnings rather than silent
     assumptions.

2. HGVS normalization improvement
   - Improve support for common cDNA, protein, and genomic HGVS forms seen in
     real submissions.
   - Preserve unresolved fields explicitly when local resolution is not possible.
   - Add warnings for ambiguous transcript accessions, incomplete alleles,
     genome-build uncertainty, and unsupported variant classes.

3. Transcript selection framework
   - Introduce an explicit transcript selection policy surface.
   - Record candidate transcripts, selected transcript, selection reason, MANE or
     canonical hints when available, and conflicts between input and annotation
     transcripts.
   - Keep transcript selection auditable and reviewable instead of hiding it
     inside criterion evaluators.

### P1: Real-Data Provider Hardening

4. gnomAD local snapshot provider refinement
   - Harden local snapshot parsing, allele-frequency field mapping, ancestry
     population handling, build metadata, and no-record semantics.
   - Keep provider misses distinct from true population absence.
   - Surface ancestry coverage limitations in evidence and reports.

5. ClinVar online real-world validation
   - Validate the existing opt-in ClinVar online pathway against real records and
     edge cases.
   - Check condition specificity, review status, variant identity matching,
     transcript/protein mismatch, and multiple-submission conflicts.
   - Preserve candidate/review-note behavior and do not auto-apply PP5/BP6.

6. Literature PubMed/LitVar read-only candidate extraction
   - Add read-only extraction of candidate literature signals from PubMed/LitVar
     metadata and snippets where available.
   - Require source identifiers, query text, retrieval time, and candidate
     rationale for each item.
   - Keep extracted PS3/BS3, PS2/PM6, PP1, PS4, and PP4 hints as review-only
     candidates.

### P2: Reporting And Workflow

7. Report Chinese localization
   - Add Chinese report rendering for review-facing sections, warnings, safety
     language, and evidence summaries.
   - Keep criterion codes, source identifiers, variant names, and classification
     values unambiguous across English and Chinese outputs.
   - Include clear wording that human review is required and the report is not a
     final clinical sign-out.

8. Batch variant input support
   - Add a batch input workflow for multiple SNV/small-indel variants.
   - Return per-variant results with independent warnings, errors, provenance,
     and review-required flags.
   - Make partial failure explicit and prevent silent row drops or merged
     evidence across variants.

## Features Not Recommended For v0.2.0

The following should remain outside v0.2.0 scope because they require additional
domain models, validation sets, clinical governance, or evidence-specific safety
controls:

- CNV, SV, and DMD complex structural variant interpretation.
- Automatic PS3 or BS3 application from functional evidence.
- Automatic PS2, PP1, or PS4 application from segregation, de novo, or case
  enrichment evidence.
- Methylation, repeat expansion, and mitochondrial interpretation.
- Direct clinical report sign-out or any workflow implying final diagnostic
  authorization.

## Risk Register

| Risk | Why It Matters | v0.2.0 Mitigation |
| --- | --- | --- |
| Pathogenic overcalling | New real-data inputs may create pressure to apply stronger evidence than the beta can safely justify. | Keep conservative criterion strength, require human review, add no-new-overcalling checks, and keep candidate evidence separate from applied criteria. |
| Transcript mismatch | ClinVar, HGVS, VEP/ANNOVAR, and user inputs may describe different transcripts or protein effects. | Add transcript selection records, mismatch warnings, transcript edge-case tests, and report-visible transcript provenance. |
| Population ancestry mismatch | Frequency thresholds can be misapplied when ancestry coverage or labels differ across snapshots. | Preserve ancestry-specific fields, document coverage gaps, avoid interpreting provider miss as absence, and add ancestry mapping tests. |
| Literature hallucination | Literature agents may overstate abstracts, infer unavailable evidence, or confuse variants. | Use read-only candidate extraction, require source identifiers and query provenance, and keep literature evidence review-only. |
| ClinVar condition mismatch | A ClinVar assertion may be valid for a different condition, inheritance model, or transcript context. | Validate condition specificity, expose condition conflicts, and keep ClinVar as review-note evidence only. |
| Batch mode silent failure | Multi-variant workflows can hide row-level parse errors, skipped variants, or mixed evidence. | Require per-row status, per-variant provenance, explicit partial-failure summaries, and tests for malformed rows. |

## Milestones

### v0.2.0-alpha1

Focus: real-data ingestion foundation.

Deliverables:

- Initial local VEP/ANNOVAR annotation adapter.
- Improved HGVS normalization warnings for common unresolved real-data cases.
- First transcript selection data model and audit trail.
- Annotation adapter unit tests and transcript mismatch fixtures.

Exit criteria:

- Existing pytest suite passes.
- Adapter tests cover valid rows, malformed rows, missing transcript fields,
  genome-build metadata, and unsupported variant classes.
- No change introduces automatic application of out-of-scope ACMG criteria.

### v0.2.0-alpha2

Focus: provider and external validation hardening.

Deliverables:

- Refined gnomAD local snapshot provider behavior.
- ClinVar online real-world validation cases for opt-in online mode.
- Expanded benchmark set draft from 21 to at least 60 cases.
- Expanded real-data smoke draft from 10 to at least 25 cases.

Exit criteria:

- Provider misses remain distinct from population absence.
- ClinVar condition, review-status, and variant-identity mismatches are visible
  as review notes or warnings.
- MCP schema contract tests cover new provider-facing fields and structured
  error paths.

### v0.2.0-beta

Focus: review workflow and beta completeness.

Deliverables:

- Read-only PubMed/LitVar candidate extraction.
- Chinese report localization.
- Batch variant input support with per-variant status.
- Benchmark expanded to 100 curated cases.
- Real-data smoke expanded to 50 cases.

Exit criteria:

- Batch mode reports partial failures explicitly.
- Literature extraction remains candidate-only and does not apply strong,
  segregation, de novo, or case-enrichment criteria.
- Chinese reports preserve safety language and evidence traceability.
- Benchmark and smoke suites pass with no new overcalling behavior.

### v0.2.0 Release

Focus: release stabilization and documentation.

Deliverables:

- Updated README and provider documentation.
- Updated known limitations and release readiness review.
- v0.2.0 release notes.
- Release tag from `develop` after review.

Exit criteria:

- Full pytest suite passes.
- 100-case benchmark passes.
- 50-case real-data smoke suite passes.
- Safety review passes.
- Documentation reflects v0.2.0 behavior and remaining limitations.
- No known new overcalling behavior is accepted into the release.

## Testing Plan

- Expand the curated benchmark suite from 21 to 100 cases.
  - Include benign, likely benign, VUS, likely pathogenic, and pathogenic
    examples.
  - Include negative controls where data are incomplete or conflicting.
  - Track expected applied criteria and expected review-only evidence.
- Expand real-data smoke testing from 10 to 50 cases.
  - Include HGVS, VCF-like, local annotation, ClinVar, and population snapshot
    examples.
  - Include no-record, mismatch, and malformed-source scenarios.
- Add transcript edge cases.
  - Cover MANE/canonical disagreement, input transcript not found in annotation,
    multiple transcript consequences, protein effect mismatch, and transcript
    version differences.
- Add annotation adapter tests.
  - Cover VEP-style and ANNOVAR-style rows, required-field validation, snapshot
    metadata, consequence parsing, unsupported variant class rejection, and
    structured row-level warnings.
- Add MCP schema contract tests.
  - Verify new input and output fields are reflected in tool schemas.
  - Verify structured errors and recoverability flags for provider failures,
    malformed batch rows, unsupported variant classes, and schema-invalid inputs.

## Git Workflow

- Continue development from `develop`.
- Use feature branches for v0.2.0 work, preferably named
  `codex/v0.2.0-<topic>` or an equivalent project branch naming convention.
- Use PR-style review before merging each feature branch.
  - Scope matches v0.2.0 plan.
  - Tests added or updated for changed behavior.
  - Evidence provenance is preserved.
  - Human-review-required behavior is unchanged.
  - No unsupported ACMG criteria are automatically applied.
  - Documentation is updated when user-visible behavior changes.
- Tag release candidates and final release from reviewed `develop`.
  - Suggested tags: `v0.2.0-alpha1`, `v0.2.0-alpha2`, `v0.2.0-beta`,
    `v0.2.0`.

## Definition Of Done

v0.2.0 is done only when all release gates pass:

- Full `pytest` suite passes.
- 100-case benchmark passes with expected criteria and classifications.
- 50-case real-data smoke suite passes without silent failures.
- Safety review passes, including review of overcalling, transcript mismatch,
  ClinVar condition mismatch, literature candidate handling, and batch mode.
- Documentation is updated for setup, providers, MCP schemas, limitations,
  benchmark, smoke testing, and release readiness.
- No new overcalling behavior is introduced.
- Every generated result and report continues to require human review.

