# MCP Tools

## Overview

The MCP server exposes auditable SNV/small indel variant interpretation tools.
Tool input schemas are intentionally strict at the MCP boundary: top-level tool
arguments use `additionalProperties: false`, required fields are explicit, enum
fields list allowed values, and arrays/objects define item or property shapes.

The server validates tool arguments before calling handlers. Invalid input
returns a JSON-RPC structured error with `SCHEMA_VALIDATION_ERROR`; it should not
crash the server or enter ACMG/provider/classification logic.

Phase 1 tools:

- `health_check`
- `rate_variant`
- `rate_variant_batch`
- `rate_annotated_variants`
- `normalize_variant`
- `query_clinvar`
- `query_population_frequency`
- `evaluate_population_rules`
- `evaluate_pvs1`
- `evaluate_computational_evidence`
- `search_literature_evidence`
- `generate_report`

## Shared Objects

`Variant` requires `variant_id`, `genome_build`, `variant_type`, `chrom`, `pos`,
`ref`, and `alt`. Allowed `genome_build` values are `GRCh37` and `GRCh38`.
Allowed `variant_type` values are `snv`, `small_insertion`, `small_deletion`,
and `small_delins`. Optional fields include `gene_symbol`, `transcript`,
`hgvs_g`, `hgvs_c`, `hgvs_p`, `zygosity`, `normalization_warnings`,
`review_flags`, and `audit_trail`.

`GeneDiseaseContext` accepts either canonical names (`gene_symbol`,
`disease_name`, `inheritance_mode`) or aliases (`gene`, `disease`,
`inheritance`). It may include phenotype terms, LoF mechanism fields,
last-exon/NMD fields, transcript, source, and audit trail.

`Transcript` requires `accession` and `gene_symbol`. Optional fields include
`version`, `hgvs_c`, `hgvs_p`, `exon`, `consequence`, `mane_select`, and
`canonical`.

`EvidenceItem` requires `evidence_id`, `code`, `strength`, `direction`,
`reason`, `source`, and `confidence`. Evidence code, strength, direction, report
format, report mode, language, genome build, variant type, zygosity, and review
flag severity are enumerated in the MCP schema.

## Flexible Fields

The following fields deliberately remain flexible because they wrap mock or
source-specific payloads:

- `rate_variant.options.clinvar_records[]`: raw mock ClinVar records.
- `rate_variant.options.literature_records[]`: raw mock literature records.
- `EvidenceSource.query`: provider query metadata.
- `EvidenceSource.provenance`: source-specific provenance payload.
- `EvidenceItem.supporting_data`: evidence-specific supporting data.
- `AuditTrail.query` and `AuditTrail.source_snapshot`: audit snapshots.

Other option containers are strict. For example, `population_thresholds`,
`computational_thresholds`, and `data_sources` reject unknown fields.

## health_check

Input: empty object only.

```json
{}
```

Output includes `status`, `service`, `stage`, `timestamp`, `checks`,
`warnings`, and `echo`.

Unknown fields are rejected with `SCHEMA_VALIDATION_ERROR`.

## rate_variant

Required input: one supported normalization shape:

- `variant` object, or
- `hgvs_c`, `hgvs`, or `value`, or
- `chrom` + `pos` + `ref` + `alt`, or
- `chromosome` + `position` + `ref` + `alt`.

Optional top-level fields: normalization fields, `gene_disease_context`,
`context`, `disease`, `inheritance`, `phenotype`, `phenotype_terms`, and
`options`.

`options` supports `mock_mode`, include toggles, `data_sources`,
`population_frequency`, `population_thresholds`, `computational_predictions`,
`computational_thresholds`, `clinvar_records`, `literature_records`,
`mock_supplemental_evidence_items`, `supplemental_evidence_items`, and
`gene_disease_context`.

Output includes normalized variant, classification result, evidence items,
final classification, report, limitations, human review status, audit trail, and
per-step results.

Invalid schema input is rejected before pipeline execution. Normalization or
downstream module failures are preserved as structured limitations inside the
pipeline result when the input schema itself is valid.

## normalize_variant

Required input: one supported normalization shape:

- `variant` object, or
- `hgvs_c`, `hgvs`, or `value`, or
- `chrom` + `pos` + `ref` + `alt`, or
- `chromosome` + `position` + `ref` + `alt`, or
- `vcf` object.

Optional fields: `input_type` (`hgvs`, `vcf_like`, `structured`), `gene`,
`gene_symbol`, `transcript`, `transcript_accession`, `hgvs_g`, `hgvs_c`,
`hgvs_p`, `chrom`, `chromosome`, `pos`, `position`, `ref`, `alt`, and
`genome_build` (`GRCh37`, `GRCh38`).

Output includes `status`, `input_format`, `normalized_variant`,
`normalization_warnings`, `unresolved_fields`, `human_review_required`,
`human_review`, and audit metadata.

Malformed or unsupported variant input returns a structured MCP error from the
normalizer. Unknown fields are rejected by schema validation.

## rate_variant_batch

Required input: either `records` as an array of record objects, or textual batch
input through `input_text`, `text`, or `data`.

Optional input:

- `input_format` or `format`: `json`, `jsonl`, `csv`, `tsv`, `vcf`, or
  `vcf_like`.
- `batch_id`: caller-supplied batch identifier.
- `options`: default options merged into each record before it is sent to the
  existing `rate_variant` pipeline.

Each record may use the same flat variant fields accepted by `rate_variant`.
Batch mode does not change ACMG logic, does not merge evidence across variants,
and does not relax safety rules. Malformed records, unsupported CNV/SV/repeat
records, symbolic VCF alleles, multi-allelic ALT values, normalization failures,
and per-record exceptions are returned as explicit `error` results and
`failed_records`; no input row is skipped silently.

Output includes `batch_id`, `total_records`, `succeeded`, `failed`, per-record
`results`, `failed_records`, `warnings`, `limitations`, `started_at`, and
`completed_at`. Successful records include the per-record
`classification_result`, `review_required`, review flags, limitations, and
normalized variant key when available.

## rate_annotated_variants

Required input: either raw annotation `records` or textual annotation input
through `input_text`, `text`, or `data`.

Optional input:

- `annotation_format`, `source_format`, or `format`: `vep`, `annovar`,
  `bcftools`, or `generic`.
- `source_version`: caller-supplied annotation provenance version.
- `delimiter`: delimiter override for text input.
- `batch_id`: caller-supplied batch identifier.
- `gene_disease_context` or `context`: optional context copied into generated
  batch records.
- `options`: default options merged into each generated `rate_variant` record.

The tool parses real annotation rows into batch `rate_variant` records, then
runs the existing batch pipeline. Annotation is descriptive only: it may provide
variant fields and transcript-selection context, but it does not directly create
ACMG evidence and does not change the classification combiner.

Successful per-variant results include `annotation_provenance`,
`normalization_identity`, `transcript_selection_summary`, `review_flags`, and
`limitations`. Malformed annotation rows are returned as explicit
`MALFORMED_ANNOTATION_RECORD` failed records; no annotation row is silently
skipped. All records remain human-review-required.

## query_clinvar

Input accepts exactly one of these strict containers or flat query fields:

- `variant`: normalized `Variant`.
- `normalized_variant`: normalized `Variant`.
- `query`: ClinVar query object.
- Flat query fields.

Supported query fields are `gene`, `gene_symbol`, `hgvs_c`, `hgvs_p`, `rsid`,
`rsID`, `variation_id`, `clinvar_variation_id`, `variationID`, `chromosome`,
`chrom`, `position`, `pos`, `ref`, `alt`, `genome_build`, and `condition`.

At least one provider-supported query shape must resolve: gene + HGVS, rsID,
ClinVar Variation ID, or genomic position + alleles.

Output includes `clinvar_records`, `candidate_evidence_items`, `review_flags`,
`limitations`, human review status, and audit/provenance. ClinVar evidence stays
candidate/review-note oriented and does not bypass ACMG evaluation.

Invalid payloads return `SCHEMA_VALIDATION_ERROR`.

## query_population_frequency

Required input: `variant` normalized `Variant`.

No optional fields are accepted.

Output includes `population_frequency`, `evidence_items` (currently empty for
retrieval only), human review status, and audit/provenance.

Missing or malformed `variant` returns `SCHEMA_VALIDATION_ERROR`.

## evaluate_population_rules

Required input: `variant`, `gene_disease_context`, and `population_frequency`.

Optional input: `thresholds` with explicit BA1/BS1/PM2 threshold fields.

Output includes ACMG population-rule `evidence_items`, human review status, and
audit limitations. Unknown threshold fields are rejected.

## evaluate_pvs1

Required input: `variant` and `gene_disease_context`.

Optional input: `transcript`.

Output includes a `pvs1` assessment block, `evidence_items`,
`criterion_assessment`, `review_flags`, human review status, and audit
limitations.

Phase 1 PVS1 does not evaluate exon-level deletions, CNVs, SV breakpoints, or
long-read evidence. Invalid payloads return `SCHEMA_VALIDATION_ERROR`.

## evaluate_computational_evidence

Required input: `variant`.

Optional input:

- `computational_predictions`: array of `ComputationalPrediction`.
- `predictions`: alias array of `ComputationalPrediction`.
- `evidence_items`: legacy alias array of `ComputationalPrediction`.
- `thresholds`: explicit PP3/BP4 threshold object.

Each prediction requires `source`, `method`, and `prediction`; optional fields
include `score`, `threshold`, `transcript`, `candidate_only`, `limitations`, and
`splice_prediction`.

Output includes `evidence_items`, `criterion_assessments`, `review_flags`,
`summary`, human review status, and audit limitations.

Unknown fields and malformed prediction arrays return `SCHEMA_VALIDATION_ERROR`.

## search_literature_evidence

Required input: `variant`.

Optional input: `gene_disease_context` or `context`.

Output includes `literature_records`, `candidate_evidence_items`,
`evidence_items`, `extracted_claims`, `review_flags`, `limitations`, human
review status, and audit/provenance.

Literature evidence remains candidate-only in this phase. Invalid payloads
return `SCHEMA_VALIDATION_ERROR`.

## generate_report

Required input: one of `classification_result`, `result`, or `classification`.

Optional input:

- `format` or `output_format`: `markdown`, `plain_text`, or `json`.
- `mode`: `concise`, `detailed`, `laboratory`, or `clinician`.
- `language`: `en` or `zh`.

Output includes `report`, `json_summary`, `content`, human review status, audit
metadata, and one selected convenience field: `markdown`, `plain_text`, or
`json_report`.

Report generation renders supplied structured results only; it does not
recalculate ACMG criteria or resolve evidence conflicts. Invalid classification
payloads or unsupported enum values return `SCHEMA_VALIDATION_ERROR`.

## Error Shape

Schema validation and handler validation errors are returned as JSON-RPC errors:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Invalid input for tool 'normalize_variant'.",
    "data": {
      "code": "SCHEMA_VALIDATION_ERROR",
      "message": "Invalid input for tool 'normalize_variant'.",
      "details": {
        "tool": "normalize_variant",
        "errors": ["$.unexpected_extra: unknown field"]
      },
      "recoverable": true
    }
  }
}
```

Runtime module failures inside a valid `rate_variant` request are captured as
pipeline limitations whenever possible, preserving audit trail continuity.
