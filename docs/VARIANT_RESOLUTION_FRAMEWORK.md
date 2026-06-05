# Variant Resolution Framework

The Variant Resolution Framework is an offline-first descriptive layer between
variant normalization and evidence generation.

```text
normalize_variant
  -> resolve_variant
  -> context consistency
  -> evidence generation
  -> classification
```

It resolves transcript, protein, coordinate, exon, and NMD context when local
fixtures are available. It does not create ACMG evidence, apply PVS1, change
PS1/PM5, or modify the classification combiner.

After the 76 mock/fixture interface audit activation, structured genomic input
is also preserved in the resolution result. When `normalize_variant` already
has `genome_build`, chromosome, position, ref, and alt, and no local resolution
fixture coordinate is available, `resolved_coordinate` inherits the normalized
coordinate with provenance `source=normalized_variant`. This inheritance applies
to any valid positive coordinate, including position 1. Placeholder HGVS-only
coordinates remain unresolved.

78B adds a resolution provider contract surface and a local real-world HGVS
smoke fixture. The new `src/variant_pathogenicity_rater/resolution/` package is
a compatibility facade over the existing `variant_resolution` layer and exposes
`ResolutionOutcome`, `ResolutionProviderResult`, `resolve_variant`, and
`resolve_hgvs_to_variant`. Provider failures are captured as `outcome=failure`
with limitations rather than exceptions.

## Scope

The resolution layer can enrich supported SNV/small-indel inputs with:

- resolved transcript context;
- protein consequence and protein accession;
- genomic coordinate, build, ref, and alt;
- exon number, exon count, and CDS position;
- NMD context: `NMD_expected`, `NMD_unlikely`, or `unknown`;
- provenance, limitations, review flags, and per-step confidence.
- optional descriptive protein consequence from Ensembl VEP output when VEP is
  explicitly enabled and local protein resolution is unavailable.
- resolution runtime metadata: provider, outcome, source version, cache hit,
  confidence, and limitations.

`normalize_variant` remains conservative. HGVS c. inputs can still normalize to
placeholder genomic fields when transcript-to-genome mapping is unavailable.
`resolve_variant` then attempts fixture-backed enrichment and returns a
separate `VariantResolutionResult`.

## Offline Provider

Default resolution uses local fixtures under:

- `data/transcript_resolution/`

Callers may also pass inline `options.transcript_resolution_records`.

The BRCA1 fixture for `NM_007294.4:c.68_69delAG` resolves to:

- transcript: `NM_007294.4`
- protein: `NP_009225.1:p.Glu23ValfsTer17`
- GRCh38 coordinate: `17:43124027 CA>C`
- exon: `2/24`
- NMD: `NMD_expected`

No network access is attempted by default. External canonicalization providers,
including ClinGen Allele Registry-style adapters, remain future optional
providers and must be explicitly gated if added.

The 78B real-world smoke fixture is
`data/transcript_resolution/real_world_smoke_resolution_v1.jsonl`. It improves
offline descriptive resolution for the 78A smoke dataset:

- `FLG NM_002016.2:c.12064A>T`: protein, consequence, and coordinate.
- `AIFM1 NM_004208.4:c.1030C>T`: protein, consequence, and coordinate.
- `GAMT NM_000156.6:c.268G>A`: protein, consequence, and coordinate.
- `PKLR NM_000298.6:c.1403C>G`: protein, consequence, and coordinate.
- `HLCS NM_001352514.2:c.1063_1064del`: protein and consequence only.

`MYH7 NM_000257.4:c.5347A>T` remains unresolved in the local smoke fixture
until a reviewed coordinate/protein source is added.

## Transcript Rules

User supplied transcript always wins. MANE Select, MANE Plus Clinical, and
canonical transcripts are recommendations only when no transcript is supplied.
The resolver does not silently replace a user transcript with MANE.

If a fixture coordinate conflicts with an explicit user/local coordinate or
allele, the user/local value is preserved and the result emits a blocking review
flag.

Local fixture coordinates enrich the downstream resolved variant only when
they do not conflict with user/local normalized coordinates. Missing local
fixtures no longer cause structured input coordinates to disappear from
`resolved_coordinate`.

Ensembl VEP transcript consequences can fill descriptive
`resolved_hgvs_p.hgvs_p` and consequence fields in `variant_resolution`. This
is a review/context bridge only: VEP predictor records still reach ACMG
classification only through the existing PP3/BP4 computational evaluator.

## Pipeline Output

`rate_variant` now preserves:

- `normalized_variant`: output from local normalization;
- `resolved_variant`: enriched variant used by downstream context/generators;
- `variant_resolution`: full descriptive resolution result;
- `variant.protein_resolution`: canonical protein resolution view;
- `variant.coordinate_resolution`: canonical coordinate resolution view;
- `variant.resolution_runtime`: canonical resolution provider outcome view;
- `step_results["resolve_variant"]`: audit payload for the resolution step.

Existing evidence generators consume the richer variant/context objects through
their normal inputs. The resolution layer itself never emits `EvidenceItem`.

## Safety Boundaries

- The ACMG combiner is unchanged.
- Resolution does not generate ACMG criteria.
- Resolution does not auto-upgrade PVS1 or PS1/PM5.
- MANE/transcript facts, coordinates, and NMD context are descriptive facts,
  not applied evidence.
- Explicit user NMD/exon context is preserved and not overwritten by fixtures.
- Missing or conflicting resolution degrades to limitations and review flags.

## Interfaces

CLI:

```bash
vpr resolve --gene BRCA1 --hgvs "NM_007294.4:c.68_69delAG"
```

MCP:

- `resolve_variant`

The MCP tool returns `resolved_transcript`, `resolved_protein`,
`resolved_coordinate`, `exon_context`, `nmd_context`, `limitations`,
`review_flags`, `resolution_steps`, and `provenance`.
