# Real Resolution Provider Validation

This document records validation for the real-resolution provider snapshot used
by the Variant Resolution Framework.

## Purpose

The validation target is descriptive resolution stability, not ACMG evidence
generation. The checked chain is:

```text
HGVS c. -> transcript -> protein consequence -> genomic coordinate
        -> exon context -> NMD context
```

The resolver remains an offline-first layer between normalization and evidence
generation. It does not create `EvidenceItem` records, apply PVS1, change
PS1/PM5, query ClinVar, or modify the classification combiner.

## Offline Snapshot

Default runtime behavior remains local/offline. The validation snapshot is:

- `data/transcript_resolution/real_resolution_provider_validation.jsonl`

The snapshot stores provider-derived transcript-resolution facts in the existing
`VariantResolutionRecord` schema:

- gene and HGVS c. identity;
- transcript, MANE/canonical context, protein accession, HGVS protein, and
  consequence;
- GRCh38 coordinate, chromosome, position, ref, alt, and optional HGVS g.;
- exon number, total exons, CDS position, and NMD context;
- source, source version, raw snapshot reference, confidence, and provenance.

Every record is scoped as `variant resolution only; not ACMG evidence`.

## Covered Variants

The focused validation set covers common real-world resolution shapes across
seven priority genes:

| Gene | Variant | Resolution shape |
| --- | --- | --- |
| BRCA1 | `NM_007294.4:c.68_69delAG` | frameshift, early exon, NMD expected |
| CFTR | `NM_000492.4:c.1521_1523delCTT` | in-frame deletion, NMD unlikely |
| GJB2 | `NM_004004.6:c.235delC` | frameshift in final exon, NMD unlikely |
| DMD | `NM_004006.3:c.7318C>T` | stop gained, large transcript, NMD expected |
| PAH | `NM_000277.3:c.1222C>T` | missense, penultimate-exon terminal-region context |
| TP53 | `NM_000546.6:c.743G>A` | missense, coordinate/protein resolution |

BRCA2 remains in scope for missing-mapping validation through unresolved
fixture behavior.

## Review Flags And Limitations

Resolution provider failures and gaps remain non-evidence signals:

- malformed snapshot records become limitations;
- missing mappings become limitations;
- build mismatches emit `RESOLUTION_BUILD_MISMATCH`;
- transcript accession mismatches emit `RESOLUTION_TRANSCRIPT_MISMATCH`;
- transcript version mismatches emit `RESOLUTION_TRANSCRIPT_VERSION_MISMATCH`;
- coordinate or allele conflicts preserve the user/local normalized value.

Build, coordinate, and allele conflicts block automatic coordinate enrichment.
Transcript mismatches preserve the input transcript. None of these review flags
applies or removes an ACMG criterion.

## Optional Online Smoke

Online resolution-provider smoke is not implemented in the default test path.
If added later, it should be explicitly gated, for example with:

```bash
VPR_ONLINE_RESOLUTION_SMOKE=1
```

The smoke should be skipped by default, timeout-bound, provenance-visible, and
failure-to-limitation only. Live provider assertions must not bypass local
snapshot validation or directly influence classification.

## Regression Coverage

`tests/test_real_resolution_provider_validation.py` verifies:

- snapshot schema completeness and provenance;
- all named variants resolve transcript, protein, coordinate, exon, and NMD;
- path-based and inline-record loading;
- malformed provider payloads as limitations;
- missing mappings as limitations;
- build, transcript, and version mismatch review flags;
- resolution success does not create evidence items or change classification;
- resolution failure does not create resolution-derived ACMG codes.

Targeted regression command:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest \
  tests/test_real_resolution_provider_validation.py \
  tests/test_variant_resolution.py \
  tests/test_rate_variant_pipeline.py
```
