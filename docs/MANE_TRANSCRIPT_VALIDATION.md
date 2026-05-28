# MANE Transcript Validation

`66_mane_transcript_validation` adds a local-fixture-first transcript metadata
validation layer for MANE, RefSeq, and Ensembl transcript support. It is
context and report support only. It does not generate ACMG evidence and does
not change the classification combiner.

## Local Fixture Schema

Default validation uses local records supplied in pipeline options such as
`transcript_metadata_records`, `transcript_metadata`, `transcript_fixture`,
`mane_transcript_fixture`, `transcript_metadata_json`, or
`transcript_metadata_jsonl`.

Each local record must include:

- `gene`
- `transcript`
- `transcript_version`
- `mane_status`
- `canonical`
- `protein_coding`
- `exon_count`
- `cds_length`
- `transcript_source`
- `genome_build`
- `protein_accession`
- `transcript_status`
- `nmd_relevance`
- `tags`
- `source_version`
- `parser_version`
- `raw_snapshot_ref`
- `retrieval_timestamp`

Missing or malformed fixture records become limitations. Missing
`source_version` is retained as a provenance limitation.

## Canonicalization Rules

Transcript comparison separates accession and version. Exact accession and
version match is the highest-confidence match. Base accession match with a
different version is a review flag and must not be treated as a silent pass.

RefSeq and Ensembl transcripts are not automatically equivalent. A local fixture
may expose both as separate records or through explicit tags/provenance, but the
validator does not infer transcript mapping from accession family alone.

Protein HGVS prefixes are checked against the local transcript
`protein_accession` when both are available. A mismatch becomes a review flag
and blocks applied PS1/PM5, leaving otherwise relevant comparator output as
candidate/review-note only.

## Selection And No-Override Policy

When a user/input transcript is supplied, it is preserved. A missing MANE or
canonical record cannot replace it. If the input transcript is absent from the
local fixture, the validator emits `USER_TRANSCRIPT_NOT_IN_TRANSCRIPT_FIXTURE`
and records a limitation.

If a MANE Select transcript exists but differs from the user transcript, the
MANE transcript is reported as recommendation context only and a review flag is
emitted. If no user transcript is supplied, MANE Select may be recommended
before canonical and protein-coding candidates, but that recommendation remains
review context only.

## Generator Boundaries

PVS1 may use transcript validation to block or downgrade transcript-dependent
confidence. Non-coding and deprecated transcript metadata block applied PVS1 and
keep the result candidate-only or unavailable under existing PVS1 safety gates.
MANE/canonical support may appear in decision context, but it cannot bypass LoF
mechanism, disease, inheritance, NMD/splice, context consistency, or manual
review requirements.

PS1/PM5 continues to require strict transcript or protein accession matching.
Transcript version mismatch, transcript metadata conflict, or protein accession
mismatch blocks applied PS1/PM5. Comparator records cannot override the query
transcript.

Transcript validation does not add evidence to the combiner. It affects only
generator context, context consistency, report sections, review flags,
limitations, and provenance.

## Outputs

`rate_variant` returns:

- top-level `transcript_validation`
- `classification_result.transcript_validation`
- `provenance.transcript_validation`
- `report.summary.transcript_validation`
- JSON report `content.transcript_validation`
- Markdown/plain text report section `Transcript Selection / MANE Validation`

Batch and annotated-batch outputs add `transcript_validation_summary` per
successful record. MCP schemas expose transcript validation options and the
classification-result `transcript_validation` field.

## Failure Behavior

Provider and fixture failures are limitations. Empty fixtures, malformed rows,
missing source version, missing records, transcript mismatch, version mismatch,
genome-build mismatch, non-coding transcript, deprecated transcript, and
transcript/protein inconsistency require review. None of these conditions
silently override user-provided gene, transcript, disease, ancestry, or genome
build context.
