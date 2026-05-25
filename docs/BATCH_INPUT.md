# Batch Variant Input

`rate_variant_batch` adds batch input orchestration around the existing
`rate_variant` pipeline. It does not change the ACMG classification combiner and
does not relax any safety rule. Each record is parsed, checked, and rated
independently in offline/mock mode by default.

## Supported Formats

Batch input can be supplied as:

- JSON array through `records` or `input_text` with `input_format: "json"`
- JSONL through `input_text` with `input_format: "jsonl"`
- CSV through `input_text` with `input_format: "csv"`
- TSV through `input_text` with `input_format: "tsv"`
- Minimal VCF-like TSV through `input_text` with `input_format: "vcf_like"` or `"vcf"`

Supported per-record fields include:

- `gene` or `gene_symbol`
- `transcript`
- `hgvs_c`
- `hgvs_p`
- `chromosome` or `chrom`
- `position` or `pos`
- `ref`
- `alt`
- `disease`
- `inheritance`
- `phenotype` or `phenotype_terms`
- `options` for optional provider/mock configuration

Minimal VCF-like input expects tab-separated columns such as:

```text
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO
17	43092919	.	A	G	.	.	.
```

Multi-allelic VCF rows are not split silently. Submit one alternate allele per
record or the row is captured as a failed record.

## Noisy Input Cleaning

Batch parsing accepts common export noise before calling the existing
`rate_variant` pipeline:

- UTF-8 BOM and mixed newline styles.
- Empty lines and comment lines, while preserving the VCF `#CHROM` header.
- Case-insensitive CSV/TSV column names and aliases such as `Gene`, `HGVSc`,
  `Chrom`, `POS`, `REF`, and `ALT`.
- Excel `Unnamed:*` columns.
- Surrounding whitespace in values.
- `chr` prefixes and `chrM`/`MT` mitochondrial labels.
- Lowercase `ref`/`alt` values.
- Simple URL/HTML escaping in HGVS fields.

Cleanup warnings are returned in top-level `warnings`; normalization warnings
also appear in each successful record's classification limitations. These
warnings are audit context only and do not change ACMG classification.

## Output Structure

The response follows the `BatchResult` schema:

- `batch_id`
- `total_records`
- `succeeded`
- `failed`
- `summary`
- `results`
- `failed_records`
- `warnings`
- `limitations`
- `started_at`
- `completed_at`

Each item in `results` includes:

- `input_index`
- `input_record_hash`
- `normalized_variant_key`
- `status`
- `classification_result` for successful records, or `error` for failed records
- `applied_evidence`
- `review_note_evidence`
- `review_required`
- `review_flags`
- `limitations`
- `annotation_provenance`
- `provenance`
- `normalization_identity`
- `transcript_selection_summary`
- `context_consistency_summary`

The top-level `summary` includes:

- `total_records`
- `succeeded`
- `failed`
- `classification_distribution`
- `review_required_count`
- `conflict_count`
- `failed_records_summary`
- `duplicate_warnings`

## Error Handling

Batch mode is failure-isolated. A malformed row, unsupported variant, failed
normalization, or unexpected per-record exception does not terminate the whole
batch. The record is added to `failed_records` and also appears in `results` with
`status: "error"`.

Malformed JSONL lines, rows with too many delimited fields, invalid positions,
unsupported CNV/SV/repeat records, symbolic VCF alleles, ambiguous `N`, `ALT=.`,
and multi-allelic ALT values are captured explicitly. No input record is skipped
silently.

Duplicate normalized variants are allowed but reported in `warnings`.

## Safety Notes

Batch mode cannot replace human review. It repeats the existing SNV/small indel
pipeline for multiple records and preserves each variant's limitations, errors,
and review flags. The batch summary is a triage aid only and does not override
per-record classifications, context conflicts, limitations, or review
requirements.

The default is offline/mock. Network-backed providers must be enabled explicitly
through existing per-record or batch `options`, and any provider limitations are
recorded per variant.

## Example MCP Commands

JSON array:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"rate_variant_batch","arguments":{"records":[{"gene":"BRCA1","transcript":"NM_007294.4","hgvs_c":"NM_007294.4:c.68A>G","chromosome":"17","position":43092919,"ref":"A","alt":"G","disease":"Hereditary breast and ovarian cancer"}]}}}' | .venv/bin/python mcp-server/server.py
```

JSONL:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"rate_variant_batch","arguments":{"input_format":"jsonl","input_text":"{\"gene\":\"BRCA1\",\"transcript\":\"NM_007294.4\",\"hgvs_c\":\"NM_007294.4:c.68A>G\",\"chromosome\":\"17\",\"position\":43092919,\"ref\":\"A\",\"alt\":\"G\",\"disease\":\"HBOC\"}"}}}' | .venv/bin/python mcp-server/server.py
```

CSV:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"rate_variant_batch","arguments":{"input_format":"csv","input_text":"gene,transcript,hgvs_c,chromosome,position,ref,alt,disease\nBRCA1,NM_007294.4,NM_007294.4:c.68A>G,17,43092919,A,G,HBOC\n"}}}' | .venv/bin/python mcp-server/server.py
```

VCF-like TSV:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"rate_variant_batch","arguments":{"input_format":"vcf_like","input_text":"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n17\t43092919\t.\tA\tG\t.\t.\t.\n"}}}' | .venv/bin/python mcp-server/server.py
```
