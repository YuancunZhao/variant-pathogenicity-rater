# HGVS Resolution Provider

78B adds a resolution-provider contract for transcript HGVS c. inputs. This is
a descriptive resolution layer only. It does not generate ACMG evidence, does
not change candidate/applied evidence boundaries, and does not modify the ACMG
classification combiner.

## Contract

The compatibility package is `src/variant_pathogenicity_rater/resolution/`.

Key surfaces:

- `ResolutionOutcome`: `success`, `partial`, `no_record`, `failure`, `skipped`.
- `ResolutionProviderResult`: provider, outcome, source version, cache hit,
  confidence, result payload, provenance, and limitations.
- `resolve_hgvs_to_variant(transcript=..., hgvs_c=..., gene=...)`: local
  HGVS resolution wrapper.
- `resolve_variant(...)`: facade over the existing `variant_resolution` layer.

Provider failures are limitation-only:

```text
outcome=failure
limitations=[...]
```

They must not raise through the pipeline.

## Offline Resolution

Default resolution remains offline. Local fixtures are loaded from
`data/transcript_resolution/`, including:

- `brca1_resolution.jsonl`
- `real_world_smoke_resolution_v1.jsonl`

The real-world fixture improves the 78A smoke cases for PKLR, FLG, AIFM1,
GAMT, and HLCS. MYH7 remains unresolved until a reviewed mapping record is
added.

## Canonical Output

The 77A canonical `variant` section now includes additive resolution fields:

```json
{
  "protein_resolution": {},
  "coordinate_resolution": {},
  "resolution_runtime": {
    "provider": "real_world_smoke_resolution_fixture",
    "outcome": "partial",
    "source_version": "real-world-smoke-resolution-v1",
    "cache_hit": null,
    "confidence": 0.52
  }
}
```

Legacy fields such as `variant_resolution`, `normalized_variant`, and
`resolved_variant` remain present.

79A-1 also emits additive provider-layer identity under `provider_identity` and
canonical `variant.provider_identity`. This contract can combine normalized
variant fields and resolution facts into provider aliases such as HGVS,
coordinate, protein change, and validated gnomAD variant ID. It remains
provider-readiness metadata only and is not ACMG evidence.

## Safety

- Resolution facts are descriptive facts, not ACMG criteria.
- VEP consequence parsing is resolution-only unless existing computational
  evaluator gates separately use provider predictions.
- 78F allows online Ensembl VEP transcript consequences to supply descriptive
  protein-change context from `hgvsp` when present or from
  `protein_start`/`amino_acids`/`consequence_terms` when `hgvsp` is absent.
  This bridge remains resolution-only and does not directly apply PP3/BP4.
- Structured user coordinates are preserved in `resolved_coordinate`.
- Missing or conflicting resolution becomes limitations and review flags.
- Provider-layer identity conflicts are review flags and limitations; they do
  not silently overwrite normalized or resolution identity.
