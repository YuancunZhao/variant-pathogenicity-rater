# v0.3.0 Release Notes

Target release: v0.3.0
Review date: 2026-06-03
Scope: internal release for controlled review of the current
SNV/small-indel interpretation assistant on `develop`.

## Summary

v0.3.0 connects the controlled internal workflow across applied evidence
generation, reviewed evidence, literature drafts, ClinGen ERepo review notes,
natural-language input, variant resolution, VCEP profile signals, local
provider validation, benchmark regression, reports, CLI, MCP, batch,
annotated-batch, and Chinese laboratory-internal reporting.

This is not a clinical validation statement. All outputs remain machine
proposals requiring qualified human review.

## Release Gate Result

- Final command:
  `PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest`
- Result: `626 passed, 1 skipped`
- Benchmark: `tests/test_benchmark_dataset.py` passed with 100 offline curated
  SNV/small-indel cases.
- Network: no network used in release review.
- Blocking issues: none after release metadata and documentation synchronization.

## Functional Scope

- Automatic applied evidence generation: `PVS1`, `BA1`, `BS1`,
  `PM2_Supporting`, `PP3`, `BP4`, `PS1`, and `PM5`.
- Manual reviewed evidence workflow: only valid explicit `reviewed_applied`
  records can enter classification.
- Literature workflow: suggested evidence can become reviewed-evidence drafts;
  drafts default to non-applied review status.
- Natural-language input: parser-only and parse-and-rate wrappers around the
  existing workflow, without evidence generation or combiner changes.
- Variant Resolution: offline descriptive transcript, protein, coordinate,
  exon, and NMD context for supported fixture-backed HGVS c. inputs.
- ClinGen ERepo: exact-match review notes, VCEP signal context, supporting
  summaries, provenance, and reviewed-evidence drafts.
- VCEP framework: signal-only review context, approved limited overrides,
  conflict/deprecated/draft handling, batch summaries, and report visibility.
- Real provider validation: ClinVar, gnomAD local snapshot, MANE transcript
  metadata, and ClinGen ERepo local/fixture validation.
- Benchmark: 100 offline curated fixture-backed SNV/small-indel cases.
- Reports: English and Chinese laboratory-internal report outputs.
- Interfaces: CLI, MCP, batch, annotated-batch, and report generation.

## Safety Boundaries

- The ACMG classification combiner is unchanged.
- Candidate/review-note evidence is visible but excluded from classification.
- Providers cannot directly classify a variant.
- ClinVar, ClinGen ERepo, and literature outputs are not automatically applied.
- VCEP signal alone does not change evidence or classification.
- Approved overrides cannot bypass generator gates, create evidence, or promote
  candidate evidence.
- Reports render supplied results only; they do not rerun evidence generation or
  change classification.
- VUS wording remains conservative and does not imply pathogenic or benign
  leaning.

## Known Non-Blocking Limitations

- Default release validation remains offline; optional online provider smoke
  gates are outside the default release gate.
- The benchmark is a safety regression set, not a clinical truth set.
- Local provider quality depends on caller-supplied source versions, snapshots,
  genome build, transcript metadata, and provenance.
- A selected real VCEP profile pilot remains future work.
- CNV/SV interpretation is not supported.

## Release Metadata

- `VERSION`: `0.3.0`
- `pyproject.toml`: `0.3.0`
- `plugin.toml`: `0.3.0`
- MCP default server version: `0.3.0`

Suggested internal tag:

```bash
git tag -a v0.3.0 -m "v0.3.0 internal release"
```
