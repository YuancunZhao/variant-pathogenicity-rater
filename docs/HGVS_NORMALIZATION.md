# HGVS / Variant Normalization

Variant normalization is an offline-first, descriptive preprocessing step for SNV and small indel inputs. It improves stable variant identity keys for downstream lookup and reporting, but it does not create ACMG evidence and does not modify the classification combiner.

## Scope

Supported local inputs:

- VCF-like fields: `chrom`/`chromosome`, `pos`/`position`, `ref`, `alt`
- HGVS-like fields: `transcript`, `hgvs_c`, optional `hgvs_p`
- SNVs and small insertions, deletions, and delins up to 50 bp
- Chromosome aliases with or without `chr` prefixes
- Common ref/alt prefix and suffix trimming where at least one base remains on both sides

Every successful normalization preserves the original user-facing fields on the `Variant` where applicable, including user transcript, HGVS c., HGVS p., and gene symbol. It also returns a `VariantIdentity` with stable keys:

- `normalized_variant_key`
- `genomic_key`
- `hgvs_key`
- `protein_key`
- `gene_variant_key`
- `input_hash`
- `normalization_status`
- `unresolved_fields`
- `provenance`

## Unsupported Cases

The local normalizer rejects or flags cases that are outside phase-1 scope:

- CNVs, inversions, translocations, repeat expansions, and other larger events
- Multi-allelic `alt` values; submit or split one alternate allele at a time
- Alleles outside `A`, `C`, `G`, `T`, or `N`
- Non-positive positions or unrecognized chromosomes
- HGVS forms that cannot be safely reduced to SNV/small-indel identity without external transcript/genome mapping

Normalization failures are captured by callers as limitations and human-review requirements. They must not crash the integrated pipeline.

## No Automatic Liftover

The normalizer never performs unsafe automatic liftover. If genome build, transcript mapping, chromosome, or position cannot be resolved locally, those fields remain unresolved and are reported through warnings, limitations, review flags, and `VariantIdentity.unresolved_fields`.

## Variant Resolution Layer

After normalization, `resolve_variant` may enrich HGVS c. inputs with local
fixture-backed transcript, protein, coordinate, exon, and NMD context. This is a
separate descriptive layer: `normalized_variant` remains the local normalization
result, while `resolved_variant` is the enriched downstream copy when resolution
is available.

Resolution is offline-first and uses local records such as
`data/transcript_resolution/brca1_resolution.jsonl`. It does not perform
automatic liftover, does not call external canonicalization services by
default, and does not create ACMG evidence. Conflicts with explicit user
coordinates or alleles are review flags rather than silent overrides.

## Online Normalizer

`OnlineVariantNormalizer` integration is optional and disabled by default. When enabled by an explicit resolver or request option, results are cached by the existing online resolver framework and included in provenance.

Online results do not silently override user input. Low-confidence results are retained only as candidate context. High-confidence results can confirm the local identity when they match; conflicts become review flags while preserving the original user input.

## Safety Boundaries

Normalization and annotation are descriptive only:

- No ACMG criteria are directly triggered by normalization.
- The classification combiner is unchanged.
- Safety rules are not relaxed.
- Human review remains required.

## Review-Required Conflicts

The following cases are surfaced for review:

- HGVS c. allele and genomic ref/alt disagree
- User transcript differs from the transcript embedded in HGVS c.
- Gene symbol conflicts with transcript metadata
- Protein HGVS is missing or incomplete
- Online normalizer candidate is low confidence or conflicts with local identity
