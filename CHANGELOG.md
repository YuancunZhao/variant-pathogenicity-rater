# Changelog

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

