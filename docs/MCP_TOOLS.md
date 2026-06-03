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
- `parse_variant_text`
- `rate_variant_from_text`
- `rate_variant_batch`
- `rate_annotated_variants`
- `normalize_variant`
- `resolve_variant`
- `query_clinvar`
- `query_population_frequency`
- `evaluate_population_rules`
- `evaluate_pvs1`
- `evaluate_computational_evidence`
- `search_literature_evidence`
- `search_and_summarize_literature`
- `assess_literature_evidence`
- `create_reviewed_evidence_draft`
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

`ReviewedEvidence` requires `acmg_code`, `strength`, `direction`,
`curator_decision`, `review_date`, `rationale`, and `evidence_status`.
Allowed statuses are `reviewed_applied`, `reviewed_rejected`, and
`needs_more_info`.

## Flexible Fields

The following fields deliberately remain flexible because they wrap mock or
source-specific payloads:

- `rate_variant.options.clinvar_records[]`: raw mock ClinVar records.
- `rate_variant.options.literature_records[]`: raw mock literature records.
- `rate_variant.options.vcep_profile_records[]`: local VCEP signal/profile
  records for the lightweight signal/override framework.
- `EvidenceSource.query`: provider query metadata.
- `EvidenceSource.provenance`: source-specific provenance payload.
- `EvidenceItem.supporting_data`: evidence-specific supporting data.
- `AuditTrail.query` and `AuditTrail.source_snapshot`: audit snapshots.

Other option containers are strict. For example, `population_thresholds`,
`computational_thresholds`, and `data_sources` reject unknown fields.

## resolve_variant

`resolve_variant` resolves descriptive transcript, protein, coordinate, exon,
and NMD context from offline fixtures. It is not an ACMG evidence tool.

Input accepts the same flat or wrapped HGVS/VCF-like variant fields as
`normalize_variant`, plus optional `options.transcript_resolution_records`.

Example:

```json
{
  "gene": "BRCA1",
  "hgvs_c": "NM_007294.4:c.68_69delAG"
}
```

Output includes `resolved_transcript`, `resolved_protein`,
`resolved_coordinate`, `exon_context`, `nmd_context`, `limitations`,
`review_flags`, `resolution_steps`, `provenance`, `resolved_variant`, and
`variant_resolution`.

Safety boundary: resolution is descriptive context only. It does not generate
ACMG evidence, does not apply PVS1, and does not modify classification.

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
`reviewed_evidence`.

`options` supports `mock_mode`, include toggles, `data_sources`,
`population_frequency`, `population_thresholds`, `computational_predictions`,
`computational_thresholds`, `clinvar_records`, `literature_records`,
`mock_supplemental_evidence_items`, `supplemental_evidence_items`,
`reviewed_evidence`, `gene_disease_context`, and VCEP profile options
`include_vcep_signals`, `apply_vcep_overrides`, `vcep_profile_records`,
`vcep_profile_file`, and `vcep_kb_dir`.

VCEP profile signals are review context only. Approved overrides require
`apply_vcep_overrides=true`, remain limited to existing generator parameters or
candidate-only downgrades, and do not modify the combiner.

Top-level `reviewed_evidence` is an explicit curator-reviewed evidence array.
Only `reviewed_applied` records can be converted into applied ACMG evidence
before the existing combiner runs.

Output includes normalized variant, classification result, evidence items,
final classification, report, limitations, human review status, audit trail, and
per-step results.

Invalid schema input is rejected before pipeline execution. Normalization or
downstream module failures are preserved as structured limitations inside the
pipeline result when the input schema itself is valid.

## parse_variant_text

Required input: `text`.

Optional input:

- `output`: `json`, `markdown`, or `markdown-zh`.
- `language`: `en` or `zh`.
- `report_mode`: `concise`, `detailed`, `laboratory`, or `clinician`.
- `options`: parser and report options, including optional
  `ai_assisted_context`, `require_context_confirmation`,
  `confirmed_context`, and `reviewed_context`.

This parser-only tool extracts structured variant input and clinical-context
review fields without running `rate_variant`. Use it for explicit two-step
workflows where Codex should show disease/HPO candidates to the user before a
rating rerun.

The top-level schema is Codex-compatible: `type: object`,
`additionalProperties: false`, required `text`, and no top-level `oneOf`,
`anyOf`, `enum`, or `not`.

## rate_variant_from_text

Required input: `text`.

Optional input:

- `output`: `json`, `markdown`, or `markdown-zh`.
- `language`: `en` or `zh`.
- `report_mode`: `concise`, `detailed`, `laboratory`, or `clinician`.
- `options`: the same strict options object used by `rate_variant`, plus
  natural-language context options:
  - `ai_assisted_context`: opt-in parser-only AI-assisted clinical-context
    candidate extraction.
  - `require_context_confirmation`: require confirmation before AI-derived
    context can be used. Defaults to true.
  - `confirmed_context`: user- or curator-confirmed context to map into the
    existing rating path.
  - `reviewed_context`: synonym for confirmed reviewed context.

The tool parses a short natural-language or HGVS-like string into structured
variant input and then calls the existing `rate_variant` workflow. The default
parser is regex/rule-based only. Optional AI-assisted disease/HPO parsing is
opt-in, provider-backed, and candidate-only. The wrapper does not generate ACMG
evidence, does not apply reviewed evidence, and does not modify the
classification combiner.

Output includes `parsed_input`, `missing_fields`, `ambiguity_warnings`,
`normalization_warnings`, `alias_candidates`, optional `ai_assisted_context`,
`context_candidates`, `confirmed_context`, `context_confirmation_required`,
nested `rate_variant_result`, `report`, and the mandatory human-review notice.
Invalid text that does not contain a supported HGVS-like or genomic-coordinate
variant shape returns `status: error` as a normal structured tool result and
does not call `rate_variant`.

Short aliases such as `185delAG` are returned as `alias_candidates` and are not
silently normalized to HGVS or genomic coordinates.

Codex tool-selection rule: natural-language, multi-line, or
HGVS+disease+inheritance mixed user text must call `rate_variant_from_text`.
Direct `rate_variant` is for already structured fields such as `gene`,
`transcript`, `hgvs_c`, `disease`, and `inheritance`. Do not pass a whole text
block containing disease or inheritance to `rate_variant.value`.
`input_type=hgvs` is only for pure HGVS variant strings, not natural-language
paragraphs.

Bad call:

```json
{
  "name": "rate_variant",
  "arguments": {
    "value": "BRCA1 NM_007294.4:c.68_69delAG\nHereditary breast and ovarian cancer syndrome\nAD",
    "input_type": "hgvs"
  }
}
```

Correct call:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nHereditary breast and ovarian cancer syndrome\nAD",
    "options": {
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

AI-assisted candidate call:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nbreast and ovarian cancer phenotype\nAD",
    "options": {
      "ai_assisted_context": true,
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

Confirmed-context rerun:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nbreast and ovarian cancer phenotype\nAD",
    "options": {
      "confirmed_context": {
        "disease_name": "hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant"
      },
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

Unconfirmed AI candidates must be shown to the user and must not be passed as
top-level applied disease context. They cannot raise confidence for PVS1,
PM2/population, PS1, PM5, or other context-sensitive evidence. AI-derived
candidate fields are returned with `requires_user_confirmation: true`.

## search_and_summarize_literature

Input: gene and variant are required. Optional fields include transcript,
disease, inheritance, phenotype, criteria, `literature_records`, PMIDs, a
caller search query, variant aliases, and explicit online opt-in flags for
PubMed and LitVar.

The tool builds a deterministic search plan, normalizes caller-supplied records,
collapses duplicate publications or families, summarizes criterion-specific
candidate support, emits `suggested_evidence`, and returns
`reviewed_evidence_drafts`.

All literature-derived evidence is candidate-only. Suggested strengths are
reviewer guidance only. Returned evidence-like items use `strength: none`,
`candidate_only: true`, `applied: false`, and `requires_review: true`.

Online PubMed and LitVar are disabled by default. If online flags are supplied
and retrieval is unavailable or fails, the tool degrades to limitations and does
not create applied evidence.

Output includes `literature_search_results`, `literature_summary`,
`criterion_summaries`, `suggested_evidence`, `review_questions`,
`blocking_flags`, `review_flags`, `duplicate_groups`, `limitations`,
`reviewed_evidence_drafts`, `query_plan`, `citations`, and provenance.

Safety boundary: this tool never calls the combiner and returns
`final_classification_changed: false`.

## create_reviewed_evidence_draft

Input: an object with `literature_assessment_json`, containing the full output
from `assess_literature_evidence`.

The tool converts literature `suggested_evidence` into draft templates for
manual curation. It preserves `source_candidate_evidence_id`, PMID, DOI,
citation, extracted claim, review questions, and provenance. It never emits
applied evidence and returns `final_classification_changed: false`.

Drafts default to `evidence_status: needs_more_info`,
`curator_decision: pending`, and `requires_manual_review: true`. A curator must
edit a draft into a strict `reviewed_applied` record before `rate_variant` can
promote it.

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
- `reviewed_evidence`: batch mapping object with `records[]` entries containing
  `input_index` and per-record `reviewed_evidence`.

Each record may use the same flat variant fields accepted by `rate_variant`.
Each record may also include its own `reviewed_evidence` array. Batch-level
reviewed evidence is mapped by `input_index` and is not silently applied to
every record.
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
- `reviewed_evidence`: batch mapping object keyed by annotation `input_index`.

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
include `score`, `threshold`, `transcript`, `hgvs_p`, `protein_change`,
`genome_build`, `candidate_only`, `limitations`, and `splice_prediction`.

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
