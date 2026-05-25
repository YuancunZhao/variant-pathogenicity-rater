# Noisy Input Handling

`beta-prep1` hardens real-world input parsing for batch, annotated-batch, and
normalization paths. The changes are intentionally limited to input hygiene and
failure isolation. They do not add ACMG rules, alter the classification
combiner, relax safety rules, perform liftover, or infer unsupported variant
types.

## Automatically Cleaned

The parsers normalize common formatting noise before invoking the existing
pipeline:

- UTF-8 BOM at the start of text or column names.
- Blank lines, metadata lines, and comment lines where a comment is not the VCF
  `#CHROM` header.
- CSV, TSV, and VCF-like column names with inconsistent case, spaces, or common
  aliases such as `HGVSc`, `Gene`, `Chrom`, `POS`, `REF`, and `ALT`.
- Excel-generated empty columns such as `Unnamed: 0`.
- Surrounding whitespace in scalar fields.
- `chr` prefixes and mitochondrial labels: `chr1`, `1`, `chrX`, `X`, `MT`, and
  `chrM` normalize to stable internal labels.
- Lowercase `ref` and `alt` values are uppercased.
- Simple URL and HTML escaping in HGVS fields, for example `%3E` to `>` and
  `&amp;` to `&`.
- Gene symbols and transcript accessions are whitespace-trimmed and normalized
  to uppercase for identity matching.

Every cleanup that changes or drops a field is reported in batch warnings,
normalization warnings, annotation limitations, or normalization provenance.

## Rejected

The system rejects inputs that cannot be interpreted safely within the current
SNV/small-indel scope:

- Non-numeric, zero, or negative positions.
- Missing required genomic fields when no usable HGVS path exists.
- Illegal allele characters.
- `ALT` equal to `.`, symbolic values such as `<DEL>`, and multi-allelic values
  such as `A,G`.
- Ambiguous `N` in explicit REF/ALT input.
- CNV, SV, repeat, and other unsupported variant types.
- Malformed JSON/JSONL records or delimited rows with more fields than the
  header.
- Annotation rows with no recognizable gene, transcript, HGVS, or dbSNP field.

Rejected records enter `failed_records` and the batch continues.

## Warnings Only

Some conditions are preserved as warning or limitation context because they do
not justify guessing:

- Missing annotation `source_version`.
- Missing genome build, which defaults according to the existing normalizer
  behavior but is not liftovered or reconciled.
- Genome build mismatch in source records.
- Duplicate normalized variant identities.
- Missing optional HGVS protein fields.

Warnings do not change classification. Classification still depends only on the
existing normalized variant, evidence modules, and ACMG combiner.
The same noisy record should therefore produce the same per-record `status` via
Python `rate_variant_batch` and CLI `vpr batch`; differences should be limited
to wrapper metadata such as output file handling.

## Why Symbolic and Multi-Allelic ALT Are Not Interpreted

Symbolic ALT values such as `<DEL>` can represent structural variants with size,
breakpoints, or semantics that are not encoded as a concrete SNV or small indel.
Multi-allelic rows encode multiple alternate alleles in one record, and splitting
them can change coordinate normalization, evidence lookup, and downstream audit
meaning. The beta-prep1 behavior is therefore conservative: capture the row as
unsupported and ask the user to provide one concrete SNV/small-indel allele per
record.

## Preparing Annotation Files

For VEP, ANNOVAR, bcftools csq, or generic tables:

- Include source name and `source_version` when possible.
- Prefer one row per transcript annotation and one concrete ALT allele per row.
- Include `chrom`, `pos`, `ref`, and `alt` when available.
- Include `gene`, `transcript`, `hgvs_c`, and `hgvs_p` when available.
- Keep VCF-like `INFO`, `FORMAT`, and sample columns if needed; they are allowed
  as extra context but not used to infer unsupported variants.
- Remove structural variants, symbolic ALT rows, and multi-allelic rows before
  rating, or expect them in `failed_records`.
