# v0.2.0-beta Release Notes

Review date: 2026-05-25
Target release: v0.2.0-beta
Scope: internal beta for controlled testing of noisy-input handling, context
consistency checks, report usability, CLI/MCP workflows, and conservative safety
boundaries.

## Summary

v0.2.0-beta is ready for internal testing. It keeps the v0.2.0-alpha2 CLI,
MCP, single-variant, batch, annotated-batch, annotation, normalization,
transcript-selection, and report workflows, then adds beta hardening around
noisy inputs, context consistency, failed-record visibility, and report
readability.

This release is not a clinical validation statement. Every machine-generated
classification remains a proposal that requires qualified human review.

## Added Since v0.2.0-alpha2

- Noisy input hardening for common batch and annotation export issues,
  including BOMs, comments, mixed-case columns, alias columns, `chr` prefixes,
  lowercase alleles, URL/HTML escaped HGVS values, ambiguous alleles,
  multiallelic-looking records, symbolic ALT values, and CNV/SV-like inputs.
- Structured failed-record handling for malformed rows and unsupported records;
  batch and annotated-batch paths do not silently skip records.
- Context consistency checks for gene, transcript, disease, inheritance,
  ancestry, consequence, provider-record, and genome-build mismatches.
- Report sections for context consistency, transcript selection, candidate
  evidence, provenance, limitations, VUS caution, and human-review-required
  safety language.
- Batch summary fields for succeeded/failed counts, classification
  distribution, review-required count, context conflicts, duplicate warnings,
  and failed-record summaries.

## Functional Gate

- Single variant: pass.
- Batch: pass.
- Annotated batch: pass.
- CLI: pass.
- MCP: pass.
- Annotation adapters: pass.
- Normalization: pass.
- Transcript selection: pass.
- Context consistency: pass.
- Report generator: pass.

## Safety Gate

- Classification combiner relaxation: none.
- Candidate evidence remains excluded from classification.
- Annotation, normalization, transcript selection, and context consistency are
  review context only, not ACMG evidence.
- ClinVar and literature outputs remain candidate/review-note only.
- SpliceAI remains computational prediction only and does not trigger PS3, BS3,
  or PVS1.
- Noisy inputs are rejected or preserved with structured warnings/errors.
- Batch workflows preserve failed records and do not skip rows silently.
- Human review remains required on all outputs.

## Known Limitations

- SNV/small-indel scope only; CNV, SV, repeat expansion, mitochondrial,
  methylation, RNA-seq, long-read, and complex rearrangement workflows remain
  out of scope.
- The offline benchmark remains alpha-sized at 21 curated cases, and the
  real-data smoke suite remains 10 curated cases. Larger benchmark/smoke
  expansion is deferred from this internal beta gate and remains a pre-final
  release task.
- Provider quality depends on the configured mock/local source. Online ClinVar
  remains opt-in and candidate-only; default release review does not use the
  network.
- Local annotation quality depends on caller-provided source versions, genome
  build, transcript fields, and provenance.

## Test Gate

Final beta gate command:

```bash
.venv/bin/python -m pytest
```

Expected beta review result: 282 passed.

