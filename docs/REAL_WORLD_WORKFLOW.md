# Real-World Annotation Workflow

This workflow connects real annotation files to the existing batch
`rate_variant` pipeline without changing ACMG classification logic.

Supported inputs:

- VEP tabular output or VEP JSON arrays.
- ANNOVAR tabular output.
- `bcftools csq`-style tabular output.
- Generic CSV/TSV annotation tables with fields such as `gene`, `transcript`,
  `hgvs_c`, `chrom`, `pos`, `ref`, and `alt`.

## Noisy Annotation Input

The workflow cleans common real-world annotation exports before adapter parsing:

- UTF-8 BOM, empty lines, metadata lines, and ordinary comment lines.
- Mixed-case or aliased columns such as `Gene`, `HGVSc`, `Chrom`, `POS`,
  `REF`, and `ALT`.
- Excel `Unnamed:*` columns.
- Surrounding whitespace in HGVS, gene, transcript, coordinate, and allele
  fields.
- URL/HTML escaped HGVS values.
- `chr` prefixes and mitochondrial labels such as `chrM` and `MT`.
- Lowercase alleles.

Cleaning is recorded as limitations or downstream normalization warnings.
Missing `source_version` is also a limitation because provenance is incomplete,
but it does not stop the batch.

## Safety Boundaries

The workflow is intentionally conservative:

- It does not modify the classification combiner.
- It does not relax annotation safety rules.
- Annotation records never directly generate ACMG evidence.
- Transcript selection is descriptive context only and remains
  human-review-required.
- Context consistency checks compare user/input context with annotation and
  provider context. They add review flags, limitations, and per-record
  summaries, but they do not change ACMG classification.
- Malformed annotation rows are returned as failed records; they are not skipped.
- Annotation rows missing key identifiers are returned as failed records instead
  of being guessed from nearby columns.
- Symbolic ALT, ambiguous `N`, and multi-allelic rows are not converted into
  SNV/small-indel records.
- Every successful and failed result keeps `review_required` true.

## Python API

Use `run_annotation_batch_workflow` for the complete path:

```python
from variant_pathogenicity_rater.pipeline.real_world import run_annotation_batch_workflow

result = run_annotation_batch_workflow(
    {
        "annotation_format": "vep",
        "input_text": vep_text,
        "source_version": "local-vep-run-2026-05-22",
        "gene_disease_context": {
            "gene": "BRCA1",
            "disease": "Hereditary breast and ovarian cancer",
            "inheritance": "autosomal dominant",
        },
    }
)
```

Use `annotation_to_batch_records` when annotations have already been parsed into
`VariantAnnotation` objects and you only need batch records.

## MCP Tool

`rate_annotated_variants` accepts either `records` or textual annotation input:

```json
{
  "annotation_format": "annovar",
  "input_text": "Chr\tStart\tEnd\tRef\tAlt\tGene.refGene\tFunc.refGene\tExonicFunc.refGene\tAAChange.refGene\n17\t43092919\t43092919\tA\tG\tBRCA1\texonic\tnonsynonymous SNV\tBRCA1:NM_007294.4:exon2:c.68A>G:p.Glu23Val\n",
  "gene_disease_context": {
    "gene": "BRCA1",
    "disease": "Hereditary breast and ovarian cancer"
  }
}
```

Output includes the normal batch report plus an `annotation_to_batch_records`
block. Each successful per-variant result includes:

- `annotation_provenance`
- `normalization_identity`
- `transcript_selection_summary`
- `context_consistency_summary`
- `applied_evidence`
- `review_note_evidence`
- `review_flags`
- `provenance`
- `limitations`

Malformed annotation rows appear in `failed_records` with
`MALFORMED_ANNOTATION_RECORD`.

## Limitations

This workflow is a real-world input bridge, not a new evidence engine. Missing
HGVS is preserved as a limitation when genomic coordinates are sufficient for
rating. If neither usable HGVS nor usable genomic coordinates are available, the
record enters the batch and fails during normal rate-variant normalization rather
than being silently dropped.

Prepare annotation files with one concrete ALT allele per row, concrete
`chrom/pos/ref/alt` fields when available, source version metadata, and HGVS
fields that match the selected transcript where possible. VCF-like `INFO`,
`FORMAT`, and sample columns may be present, but they are not used to infer
structural or symbolic variants.
