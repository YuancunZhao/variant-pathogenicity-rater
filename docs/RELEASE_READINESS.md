# Release Readiness Review

Review date: 2026-05-22
Target release: v0.1.0
Scope: internal testing beta for the SNV/small-indel ACMG prototype

## Summary

The current project is ready for an internal v0.1.0 test release. The full
pytest suite passed with 178 passed tests in the target environment. The
implementation is offline-first by default, exposes the intended MCP tools, has
a working `rate_variant` pipeline, and documents the key safety boundaries for
candidate evidence and human review.

This readiness conclusion is limited to internal prototype testing. It is not a
clinical validation statement.

Release gate record:

- Test result: 178 passed
- Blocking issues: no blocking issues
- Provider/network posture: offline default
- Safety posture: human review required

## Blocking Issues

No blocking release issues were found in the reviewed source and documentation.

## Non-Blocking Issues

- README now includes a clearer fresh-install path, but internal users should
  still know how to enable a local Codex Plugin from this repository in their
  own Codex environment.
- MCP tool schemas are intentionally permissive in several places
  (`additionalProperties: true`) to preserve prototype flexibility. This is
  acceptable for v0.1.0, but stricter schemas should be considered before wider
  release.
- Provider docs describe local-file contracts, but supplied production-grade
  snapshot validation and source-version governance are outside v0.1.0 scope.

## Installation And Run

Status: ready for internal testing.

- `README.md` documents creating `.venv`, installing with
  `.venv/bin/python -m pip install -e ".[dev]"`, running tests, and checking the
  environment.
- MCP server startup is documented as
  `.venv/bin/python mcp-server/server.py`.
- `plugin.toml` points Codex Plugin execution at the same MCP server command
  over stdio.

## Core Functionality

Status: ready for internal testing.

- `rate_variant` orchestrates normalization, configured provider retrieval,
  population rules, computational rules, PVS1, ClinVar review notes, literature
  review notes, classification combining, and report generation.
- `normalize_variant` supports HGVS-like and VCF-like phase-1 inputs with
  unresolved-field warnings.
- ClinVar mock/local-file/online-gated provider behavior is configurable.
- Population mock/local-file provider behavior is configurable.
- SpliceAI-style local computational input is configurable through
  computational `local_file` mode.
- Report generation supports structured report output and markdown/plain/json
  rendering paths.

## Safety Boundary Review

Status: ready for internal testing.

- Human review is required on conclusions and reports.
- ClinVar assertions are candidate/review-note only and do not auto-apply
  PP5/BP6.
- PM2 is downgraded to supporting strength in this prototype.
- Provider misses explicitly avoid treating "no record found" as population
  absence.
- SpliceAI does not trigger PS3, BS3, or PVS1.
- Literature-derived strong evidence hints are candidate-only and not applied.

## Configuration Review

Status: ready for internal testing.

- Data source defaults are documented in README and implemented in
  `src/variant_pathogenicity_rater/config/data_sources.yaml`.
- Environment-variable overrides are documented in README and provider docs.
- Offline `mock` mode is the default.
- Online ClinVar requires explicit `mode=online` or `future_online` plus
  `online_enabled=true`.

## Test And Smoke Review

Status: ready for internal testing.

- Final local pytest gate recorded for v0.1.0: 178 passed.

- `docs/BENCHMARK.md` documents the curated benchmark suite.
- `docs/REAL_DATA_SMOKE.md` documents the real-data smoke suite.
- `scripts/check_env.py` reports Python, package, pytest, project, and MCP
  import status.
- `scripts/test.sh` runs pytest through `.venv/bin/python`.

## MCP And Plugin Review

Status: ready for internal testing.

- `plugin.toml` exists and declares plugin, server, MCP, and tool-discovery
  configuration.
- MCP tools are documented in `docs/MCP_TOOLS.md`.
- Tool errors use structured `McpToolError` fields: `code`, `message`,
  `details`, and `recoverable`.
- Pipeline step failures are returned as structured limitations so the pipeline
  can continue conservatively where possible.

## Documentation Review

Status: ready for internal testing.

Reviewed documentation:

- `README.md`
- `docs/BENCHMARK.md`
- `docs/CLINVAR_PROVIDER.md`
- `docs/POPULATION_PROVIDER.md`
- `docs/SPLICEAI_PROVIDER.md`
- `docs/REAL_DATA_SMOKE.md`
- `docs/ARCHITECTURE.md`
- `docs/MCP_TOOLS.md`
- `docs/KNOWN_LIMITATIONS.md`
