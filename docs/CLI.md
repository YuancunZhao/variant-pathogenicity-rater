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
vpr resolve
vpr rate-text
vpr batch
vpr annotated-batch
vpr literature-draft-reviewed
vpr check-env
```

## Variant Resolution

`vpr resolve` runs offline fixture-backed variant resolution only. It does not
generate ACMG evidence, does not run the combiner, and does not change safety
rules.

```bash
vpr resolve --gene BRCA1 --hgvs "NM_007294.4:c.68_69delAG"
```

JSON output includes `normalized_variant`, `resolved_variant`, and
`variant_resolution` with transcript, protein, coordinate, exon, NMD,
limitations, review flags, and provenance.

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

Chinese laboratory-internal report output:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown-zh
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown --language zh --report-mode laboratory
```

Chinese reports are presentation-only. They render the supplied
`ClassificationResult` in laboratory internal review wording and do not modify
evidence generation, the ACMG combiner, or safety rules.

Manual reviewed evidence can be supplied explicitly:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G \
  --reviewed-evidence examples/reviewed_evidence.json
```

Local VCEP profile signals and approved limited overrides are explicit options:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68_69delAG \
  --include-vcep-signals --vcep-profile-file knowledge_base/disease_profiles/brca1.json

vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68_69delAG \
  --include-vcep-signals --apply-vcep-overrides --vcep-kb-dir knowledge_base
```

VCEP signals are review context only. Overrides require an approved,
non-conflicting profile and `--apply-vcep-overrides`; they do not modify the
combiner.

## Natural-Language Variant Text

`rate-text` parses a short natural-language or HGVS-like string into structured
variant input, then calls the same existing `rate_variant` workflow. The default
parser is regex/rule-based only: it does not call an LLM, does not use the
network, does not generate evidence, and does not modify the classification
combiner.

```bash
vpr rate-text --text "BRCA1 NM_007294.4:c.68_69delAG, HBOC, AD"
vpr rate-text --text "评估 BRCA1 185delAG，遗传性乳腺卵巢癌综合征，常染色体显性遗传"
vpr rate-text --text "GRCh38 chr17:43124027 CA>C BRCA1" --output markdown-zh
vpr rate-text --text "BRCA1 NM_007294.4:c.68_69delAG, breast and ovarian cancer phenotype" \
  --ai-assisted-context
```

JSON output includes `parsed_input`, `missing_fields`, `ambiguity_warnings`,
`normalization_warnings`, `alias_candidates`, context-candidate fields, and
nested `rate_variant_result`. Markdown output prepends parsed-input and
clinical-context review blocks so the user can verify the parser result before
reading the report.

`--ai-assisted-context` is opt-in and only returns candidate disease/HPO
context when an AI context parser provider is available. Candidates remain
review-only and are not used as applied context. To use a reviewed candidate,
rerun with `--confirmed-context` pointing to a JSON file or inline JSON object:

```bash
vpr rate-text --text "BRCA1 NM_007294.4:c.68_69delAG, breast and ovarian cancer phenotype" \
  --confirmed-context '{"disease_name":"hereditary breast and ovarian cancer syndrome","inheritance":"autosomal_dominant"}'
```

Short aliases such as `185delAG` are retained as `alias_candidates` unless an
explicit dictionary entry exists. They are not silently normalized to HGVS.

See [NATURAL_LANGUAGE_INPUT.md](NATURAL_LANGUAGE_INPUT.md).
See [AI_ASSISTED_CONTEXT_PARSING.md](AI_ASSISTED_CONTEXT_PARSING.md) for the
optional candidate-context workflow.

## Batch Variants

Supported input formats are `json`, `jsonl`, `csv`, `tsv`, and `vcf-like`.
Supported output formats are `json` and `jsonl`.

```bash
vpr batch --input variants.jsonl --format jsonl
vpr batch --input variants.tsv --format tsv --output result.json
vpr batch --input variants.vcf.tsv --format vcf-like --output-format jsonl
vpr batch --input variants.jsonl --format jsonl --language zh
```

`--language zh` adds a Chinese `summary_zh` triage note while preserving the
stable per-record output and existing `summary` fields.

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
