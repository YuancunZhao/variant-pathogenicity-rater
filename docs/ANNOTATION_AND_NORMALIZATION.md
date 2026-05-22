# Annotation and Normalization Framework

Variant Pathogenicity Rater supports an offline-first annotation and normalization framework for
turning common annotation outputs into a single internal schema. The framework is intentionally
descriptive: annotation and normalization results can help reviewers understand transcript context,
but they do not directly create ACMG evidence and they do not change the classification combiner.

## Offline Default

The default behavior is offline/mock. Local adapters parse fixture or file content without network
access. Online normalization and transcript metadata resolvers are disabled unless callers
explicitly set both `enabled=True` and `online_enabled=True` on the resolver configuration.

If an online lookup fails, the failure is returned as a limitation. It must not crash the pipeline.

## Internal Annotation Schema

Each parsed annotation is represented as `VariantAnnotation` with:

- `gene`
- `transcript`
- `hgvs_c`
- `hgvs_p`
- `consequence`
- `exon`
- `intron`
- `canonical`
- `mane_select`
- `transcript_biotype`
- `consequence_terms`
- `splice_region`
- `loftee_flags`
- `dbsnp_id`
- `annotation_source`
- `provenance`

`loftee_flags` is a placeholder for LOFTEE fields. It is stored for review context only.

## Supported Local Adapters

The adapter base class is `AnnotationAdapter`. It defines:

- `parse_record`
- `normalize_annotation`
- `validate_annotation`
- `source_name`
- `source_version`
- `provenance`

Implemented local adapters:

- `VepAdapter` for VEP TSV and JSON-style fixture records
- `AnnovarAdapter` for ANNOVAR `multianno` TSV records
- `BcftoolsCsqAdapter` for TSV exports containing `BCSQ`
- `GenericTableAdapter` for generic TSV/CSV records with common field names

Malformed rows are skipped and reported in `limitations`.

## Optional Online Mode

Optional online resolvers are provided as explicit opt-in extension points:

- `OnlineVariantNormalizer`
- `TranscriptMetadataResolver`

Both use `OnlineResolverConfig`, `DiskCache`, request timeouts, and injectable fetchers. A resolver
does not attempt online work unless both `enabled` and `online_enabled` are true.

All successful online results include provenance with:

- `source`
- `version`
- `query`
- `retrieved_at`
- `raw_record_hash`

The cached payload also records source, source version, query, retrieval time, and raw payload.

## Provenance and Caching

Local adapters attach `ProvenanceMetadata` to every parsed annotation. Online resolvers attach
`ProvenanceMetadata` to every successful result and cache the raw wrapped payload using the existing
`DiskCache`.

The provenance hash is computed from canonical JSON for the raw record. This allows reviewers to
detect when a source payload changed without treating source data as automatically valid evidence.

## Safety Behavior

The framework reports:

- transcript mismatch as a review flag
- multiple transcript ambiguity as a review flag
- missing HGVS as a limitation
- malformed annotation rows as limitations
- online resolver failures as limitations

MANE Select and canonical transcript labels may assist transcript selection. They are never ACMG
evidence by themselves.

Annotation and normalization are not evidence generators. They must not directly set ACMG criteria,
and the classification combiner remains unchanged.

## Transcript Ambiguity Risks

Different tools may report different transcripts, transcript versions, or consequence strings for
the same genomic variant. This is expected and clinically important. The framework preserves those
differences, records provenance, and raises review flags when multiple transcripts or transcript
mismatches are observed.
