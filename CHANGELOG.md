# Changelog

## 0.3.0 - 2026-06-02

Internal release for controlled review of the end-to-end SNV/small-indel
interpretation assistant.

### Added

- Applied evidence generation coverage for `PVS1`, `BA1`, `BS1`,
  `PM2_Supporting`, `PP3`, `BP4`, `PS1`, and `PM5`.
- Manual reviewed evidence workflow requiring explicit `reviewed_applied`
  curator records before non-automatic criteria can enter classification.
- Literature suggested-evidence to reviewed-draft workflow, with drafts
  defaulting to non-applied review status.
- ClinGen ERepo review-note integration and reviewed-evidence draft support.
- VCEP signal/override framework with signal-only profile context and limited
  approved override behavior.
- Real provider validation for ClinVar, gnomAD local snapshots, MANE transcript
  metadata, and ClinGen ERepo local/fixture workflows.
- 100-case offline curated benchmark with provider fixture references.
- Chinese laboratory-internal report template for markdown, plain text, and JSON
  report output.
- Release notes and readiness review for v0.3.0 internal release.

### Safety Notes

- ACMG business logic and the classification combiner were not changed for this
  release review.
- Candidate evidence remains excluded from classification.
- Reviewed evidence is counted only when a valid record explicitly sets
  `evidence_status=reviewed_applied`.
- Providers supply facts, review notes, or drafts only; they cannot directly
  classify a variant.
- ClinVar, ClinGen ERepo, and literature outputs are not automatically applied.
- VCEP signals alone do not change evidence or classification.
- Approved VCEP overrides cannot bypass generator safety gates, create evidence,
  or promote candidate evidence.
- VUS wording remains conservative in English and Chinese report output.

## 0.2.0-beta - 2026-05-25

Internal beta release review for controlled testing on
`feature/beta-gap-analysis`.

### Added

- Noisy input hardening for single, batch, and annotated-batch workflows,
  including structured handling for malformed rows, unsupported CNV/SV-like
  inputs, ambiguous alleles, multiallelic records, and common export noise.
- Context consistency checks for gene, transcript, disease, inheritance,
  ancestry, provider-record, and genome-build mismatches.
- Report usability refinements that separate applied ACMG evidence from
  candidate/review-note evidence, context checks, transcript selection,
  provenance, limitations, and human-review-required language.
- Batch summaries for review-required counts, context conflicts, failed-record
  summaries, duplicate warnings, and classification distribution.
- Release notes and readiness review for v0.2.0-beta internal testing.

### Safety Notes

- ACMG business logic and the classification combiner were not changed.
- Candidate evidence remains excluded from classification.
- Annotation, normalization, transcript selection, and context consistency
  remain review context only and do not generate ACMG evidence.
- ClinVar and literature evidence remain candidate/review-note only.
- SpliceAI remains computational splice prediction only and does not trigger
  PS3, BS3, or PVS1.
- Malformed or unsupported batch/annotation records are preserved explicitly
  instead of skipped silently.
- Human review remains required on every result, report, batch record, and
  failed record.

## 0.2.0-alpha2 - 2026-05-25

Internal alpha release review for CLI and real-world annotation batch workflow
testing on `develop`.

### Added

- `vpr` CLI with `rate`, `batch`, `annotated-batch`, and `check-env`
  commands.
- CLI stdout and file-output paths for single variant, batch, and annotated
  batch workflows.
- Real-world annotation batch workflow that connects VEP, ANNOVAR, bcftools
  csq, and generic annotation rows to normalization, transcript selection, and
  batch rating.
- MCP `rate_annotated_variants` workflow with schema validation and per-record
  provenance.
- Per-record failed annotation and batch records so malformed rows are reported
  instead of silently dropped.
- Release notes and readiness review for v0.2.0-alpha2 internal testing.

### Safety Notes

- ACMG business logic and the classification combiner were not changed.
- Annotation remains descriptive input only and does not directly generate
  ACMG evidence.
- ClinVar/literature candidate evidence remains candidate-only and is not
  counted in classification.
- Human review remains required on single, batch, annotated batch, report, and
  failed-record outputs.
- Batch summaries preserve per-record review flags and do not override
  record-level review requirements.

## 0.2.0-alpha1 - 2026-05-22

Internal alpha release for controlled testing of the v0.2.0 ingestion and safety
framework.

### Added

- Batch `rate_variant_batch` workflow for JSON, JSONL, CSV/TSV, and minimal
  VCF-like SNV/small-indel inputs with per-record result, warning, and failure
  reporting.
- Annotation and normalization framework with local VEP, ANNOVAR, bcftools csq,
  and generic table adapters.
- Transcript selection review framework with candidate/rejected transcripts,
  provenance, limitations, and review flags.
- HGVS and variant identity normalization refinements, including stable
  normalized keys, unresolved-field tracking, and conflict warnings.
- MCP tool schema hardening with strict top-level tool schemas and structured
  validation errors.
- Release documentation for batch input, HGVS normalization, transcript
  selection, annotation/normalization, literature safety, MCP tools, and
  v0.2.0 planning.

### Safety Notes

- Human review remains required for every result and report.
- ClinVar and literature outputs remain candidate/review-note only and do not
  participate in final classification.
- SpliceAI-style data contributes only to computational PP3/BP4 support and
  does not trigger PS3, BS3, or PVS1.
- Annotation, normalization, and transcript selection do not generate ACMG
  evidence.
- Batch mode records malformed or unsupported variants explicitly instead of
  silently skipping them.
- ACMG business logic and the classification combiner were not changed for this
  release review.

## 0.1.0 - 2026-05-22

Initial internal-test prototype for SNV/small-indel ACMG rating.

### Added

- Offline-first `rate_variant` pipeline covering normalization, population
  BA1/BS1/PM2 evaluation, computational PP3/BP4 evaluation, SNV/small-indel
  PVS1 evaluation, candidate-only ClinVar and literature review notes, ACMG
  combining, and report generation.
- MCP stdio server with dynamic tool registration and structured JSON-RPC
  errors.
- Codex Plugin configuration in `plugin.toml`.
- Mock and local-file provider framework for ClinVar, population,
  computational/SpliceAI-style, and literature inputs.
- Optional ClinVar online provider behind explicit `mode=online` and
  `online_enabled=true` gates.
- Offline benchmark and real-data smoke suites for release regression checks.
- Release readiness and known-limitations documentation.

### Safety Notes

- All classifications are machine proposals and require qualified human review.
- ClinVar and literature evidence are candidate/review-note only.
- SpliceAI contributes only to computational PP3/BP4 support and cannot trigger
  PS3, BS3, or PVS1.
- No population record found is not interpreted as population absence.
