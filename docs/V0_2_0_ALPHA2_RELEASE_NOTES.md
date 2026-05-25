# v0.2.0-alpha2 Release Notes

Release date: 2026-05-25
Release type: internal alpha for controlled testing
Base branch: `develop`

## Summary

v0.2.0-alpha2 is an internal test release for the CLI and real-world annotation
batch workflow added after v0.2.0-alpha1. It keeps the same conservative
SNV/small-indel ACMG pipeline and adds terminal access, annotated batch rating,
MCP schema coverage, and release-readiness documentation.

This release is not a clinical validation statement. All classifications remain
machine proposals and require qualified human review.

## Added Since v0.2.0-alpha1

- CLI entry point `vpr`.
- CLI commands: `rate`, `batch`, `annotated-batch`, and `check-env`.
- CLI JSON, JSONL, Markdown/stdout, and file-output paths.
- Real-world annotation workflow from annotation adapter to normalization,
  transcript selection, and batch `rate_variant` execution.
- MCP `rate_annotated_variants` tool for annotated batch workflows.
- Per-record annotation provenance, normalization identity, transcript-selection
  summaries, review flags, limitations, and failed-record reporting.
- Documentation updates for CLI, real-world workflow, batch input, MCP tools,
  known limitations, changelog, and release readiness.

## Functional Readiness

- `vpr rate` runs the existing offline/mock-backed single-variant pipeline.
- `vpr batch` parses JSON, JSONL, CSV/TSV, and VCF-like inputs and writes JSON
  or JSONL to stdout or a file.
- `vpr annotated-batch` parses VEP, ANNOVAR, bcftools csq, and generic
  annotation input, then routes generated records through batch rating.
- `vpr check-env` reports the local Python, package, pytest, project import,
  and MCP import status.
- MCP `rate_variant`, `rate_variant_batch`, and `rate_annotated_variants`
  validate schemas and preserve structured errors for invalid input.
- Malformed batch or annotation records are retained in `failed_records` and
  mirrored in per-record `results`.

## Safety Boundaries

- ACMG business logic and the classification combiner were not changed.
- The classification combiner remains conservative and candidate evidence is
  not counted.
- Annotation does not directly generate ACMG evidence.
- ClinVar and literature records remain candidate/review-note only.
- Human review remains required for every result and report.
- Batch summaries do not hide per-record review flags, limitations, or failed
  records.
- The default workflow remains offline/mock and does not use the network.

## Test Gate

Final release-review command:

```bash
.venv/bin/python -m pytest
```

Final alpha2 gate: 244 passed.

## Known Limits

- SNV/small-indel only; CNV, SV, repeat expansion, mitochondrial, methylation,
  long-read, and RNA-seq workflows remain out of scope.
- Default provider mode remains offline/mock.
- Online ClinVar remains opt-in and candidate-only.
- Population, literature, and computational online providers are not
  implemented for v0.2.0-alpha2.
- Annotation workflow quality depends on caller-supplied annotation files,
  genome build, transcript data, source version, and local provenance.
