# v0.2.0-alpha1 Release Notes

Release date: 2026-05-22
Release type: internal alpha for controlled testing
Base branch: `develop`

## Summary

v0.2.0-alpha1 advances Variant Pathogenicity Rater from the v0.1.0 internal
prototype toward the v0.2.0 ingestion and review framework. This alpha focuses
on safer input handling, annotation context, transcript selection review notes,
MCP schema hardening, and batch orchestration around the existing
SNV/small-indel `rate_variant` pipeline.

This release is not a clinical validation statement. All classifications remain
machine proposals and require qualified human review.

## Added Since v0.1.0

- Literature agent safety framework with citation-preserving candidate evidence.
- MCP tool schema hardening and structured schema validation errors.
- Annotation and normalization framework for local annotation records.
- Transcript selection framework with review flags and provenance.
- HGVS and variant identity normalization refinements.
- Batch variant input framework through `rate_variant_batch`.
- Documentation for batch input, HGVS normalization, transcript selection,
  annotation/normalization, literature safety, MCP tools, known limitations, and
  v0.2.0 planning.

## Functional Readiness

- `rate_variant` remains the single-variant integrated pipeline.
- `rate_variant_batch` calls `rate_variant` independently per record and reports
  malformed or unsupported records explicitly.
- Normalization returns stable identity keys, unresolved fields, warnings, and
  provenance while preserving human-review requirements.
- Annotation adapters and transcript selection produce review context only.
- ClinVar, population, SpliceAI-style computational, literature, and report
  paths are covered by focused tests and smoke suites.

## Safety Boundaries

- `human_review_required` remains true on classifications and reports.
- Candidate evidence is not counted by the ACMG combiner.
- ClinVar assertions remain candidate/review-note only; PP5/BP6 are not
  automatically applied.
- Literature-derived PS3, BS3, PS2, PM6, PP1, PS4, and PP4 signals remain
  candidate-only.
- SpliceAI-style data does not trigger PS3, BS3, or PVS1.
- Annotation, normalization, and transcript selection do not generate evidence.
- Batch mode does not silently skip failed rows.
- ACMG business logic and the classification combiner are unchanged by this
  release review.

## Test Gate

Final release-review command:

```bash
.venv/bin/python -m pytest
```

Final alpha1 gate: 228 passed, including benchmark, real-data smoke, MCP smoke,
and batch tests.

## Known Limits

- SNV/small-indel only; CNV, SV, repeat expansion, mitochondrial, methylation,
  long-read, and RNA-seq workflows remain out of scope.
- Default provider mode remains offline/mock.
- Online ClinVar remains opt-in and candidate-only.
- Population, literature, and computational online providers are not implemented
  for v0.2.0-alpha1.
- Local annotation and provider quality depends on caller-supplied snapshots and
  provenance.
