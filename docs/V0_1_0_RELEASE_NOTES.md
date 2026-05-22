# v0.1.0 Release Notes

Release date: 2026-05-22
Release type: internal prototype

## Summary

Variant Pathogenicity Rater v0.1.0 is the first internal prototype release of
the offline-first SNV/small-indel ACMG rating workflow. It packages the Codex
Plugin configuration, MCP stdio server, modular evidence providers, integrated
`rate_variant` pipeline, report generation, and release-readiness documentation
needed for controlled internal testing.

This release is not clinically validated. All generated classifications and
reports are machine proposals and require qualified human review.

## Included

- Offline-first `rate_variant` pipeline covering normalization, provider-backed
  evidence retrieval, population BA1/BS1/PM2 evaluation, computational PP3/BP4
  evaluation, SNV/small-indel PVS1 evaluation, ACMG combining, and report
  generation.
- MCP tools for health checks, variant normalization, ClinVar review-note
  lookup, population frequency lookup, computational evidence evaluation,
  literature review-note lookup, PVS1 evaluation, classification, reporting,
  and the integrated workflow.
- Mock and local-file provider framework for default offline operation.
- Optional ClinVar online provider behind explicit opt-in gates only.
- Benchmark, real-data smoke, provider, architecture, MCP, limitations, and
  release-readiness documentation.
- Internal regression gate recorded as 178 passed tests.

## Safety Boundaries

- Human review is always required.
- ClinVar and literature outputs are candidate/review-note evidence only.
- SpliceAI-style evidence supports PP3/BP4 only and does not trigger PS3, BS3,
  or PVS1.
- Provider misses are not interpreted as population absence.
- Default operation is offline and mock-backed.

## Validation

- Release readiness review recorded no blocking issues.
- Final local test gate for this release: `178 passed`.

