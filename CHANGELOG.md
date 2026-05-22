# Changelog

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
