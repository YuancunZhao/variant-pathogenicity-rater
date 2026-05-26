# Variant Pathogenicity Rater CLI

The `vpr` command exposes the existing offline/mock-backed workflows from the
terminal. It does not modify the ACMG classification combiner, does not relax
safety checks, and annotation inputs remain descriptive context only. Annotation
records never directly generate ACMG evidence.

Install the project in editable mode first:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

## Commands

```bash
vpr rate
vpr batch
vpr annotated-batch
vpr literature-draft-reviewed
vpr check-env
```

## Single Variant

JSON is written to stdout by default:

```bash
vpr rate \
  --gene BRCA1 \
  --transcript NM_007294.4 \
  --hgvs-c NM_007294.4:c.68_69delAG \
  --hgvs-p NP_009225.1:p.Glu23ValfsTer17 \
  --chromosome 17 \
  --position 43092919 \
  --ref AG \
  --alt A \
  --disease "Hereditary breast and ovarian cancer" \
  --inheritance "autosomal dominant"
```

Markdown report output:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown
```

Manual reviewed evidence can be supplied explicitly:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G \
  --reviewed-evidence examples/reviewed_evidence.json
```

## Batch Variants

Supported input formats are `json`, `jsonl`, `csv`, `tsv`, and `vcf-like`.
Supported output formats are `json` and `jsonl`.

```bash
vpr batch --input variants.jsonl --format jsonl
vpr batch --input variants.tsv --format tsv --output result.json
vpr batch --input variants.vcf.tsv --format vcf-like --output-format jsonl
```

Batch reviewed evidence uses a JSON file with `records` entries keyed by
`input_index`; it is not silently applied to every record:

```bash
vpr batch --input variants.jsonl --format jsonl --reviewed-evidence reviewed-batch.json
```

Per-record errors are preserved in `failed_records` and summarized with
`failed > 0`. By default, partial batch failures return exit code `0` so
successful records remain usable. Use `--no-continue-on-error` to return a
non-zero exit code when any record fails.

Fatal input/configuration problems, such as an unreadable file or unsupported
format, return a non-zero exit code and write the error to stderr.

## Annotated Batch

Supported annotation sources are `vep`, `annovar`, `bcftools`, and `generic`.
The CLI parses annotations, records safety limitations and transcript-selection
review metadata, then calls the same annotated batch workflow used by the
Python API and MCP `rate_annotated_variants` tool.

```bash
vpr annotated-batch --input vep.tsv --source vep --include-report
vpr annotated-batch --input annovar.tsv --source annovar --output annovar-results.json
vpr annotated-batch --input csq.tsv --source bcftools --output-format jsonl
```

`annotated-batch` also accepts `--reviewed-evidence` using the same
`input_index` mapping shape as batch mode.

`--include-report` copies report text from each classification result into the
per-record batch result when available.

Annotated-batch JSON wraps the normal batch result under `batch`. Each
successful per-record result preserves `normalization_identity`,
`transcript_selection_summary`, `context_consistency_summary`,
`applied_evidence`, `review_note_evidence`, `review_flags`, `provenance`, and
`limitations`. Annotation-derived fields are descriptive context only and do not
generate ACMG evidence.

## Literature Draft Reviewed

`literature-draft-reviewed` converts `assess_literature_evidence` JSON output
into manual reviewed-evidence draft templates. The command does not apply
evidence and does not call the classification combiner.

```bash
vpr literature-draft-reviewed \
  --literature-assessment-json examples/literature_agent_output.json \
  --output reviewed_draft.json
```

Draft records default to `needs_more_info` and `curator_decision: pending`.
A curator must explicitly edit a record to `reviewed_applied` before using it
with `vpr rate --reviewed-evidence`.

## Environment Check

```bash
vpr check-env
```

This command reuses the local environment diagnostics from `scripts/check_env.py`.
