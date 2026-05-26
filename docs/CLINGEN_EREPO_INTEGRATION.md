# ClinGen Evidence Repository Integration

ClinGen Evidence Repository integration is a conservative review-note framework.
It surfaces VCEP curation activity, exact variant curated assertions, supporting
summaries, citations, and draft reviewed-evidence templates. It does not change
the ACMG classification combiner and does not automatically apply ACMG evidence.

## Data Sources

- Default mode is offline/mock or local-file.
- Local snapshots may be JSON, JSONL, CSV, or TSV.
- Optional online mode requires explicit `online_enabled=true` and uses cache,
  source URL/API endpoint, retrieval timestamp, parser version, raw snapshot
  hash, and limitations.
- ClinGen Allele Registry CA IDs are accepted as query identifiers when supplied.
  Automated external CA ID normalization remains opt-in/future work.
- ClinVar Variation ID can be used as an optional cross-database identifier.

## Matching

Match priority is CA ID, ClinVar Variation ID, normalized genomic allele,
transcript/HGVS, protein-only, then gene-only. Protein-only matches are
candidate context and never exact. Gene-only matches are VCEP activity signals,
not variant matches.

Condition mismatch blocks high-confidence exact matching. Transcript mismatch,
stale or unversioned classifications, incomplete provenance, and conflicting
ClinVar/ERepo assertions create review flags or limitations.

## Safety

ERepo classifications and VCEP criteria are external curated assertions for
review. They are emitted as candidate/review-note evidence with
`strength=none`, `candidate_only=true`, and `applied=false`.

Reviewed-evidence drafts generated from ERepo matches default to
`needs_more_info`. A qualified curator must edit and submit a valid
`reviewed_applied` record through the existing manual reviewed evidence workflow
before any evidence can affect classification.

## Interfaces

- `rate_variant` option: `include_clingen_erepo`.
- Local-file configuration: `data_sources.sources.clingen_erepo.local_file`.
- CLI flags: `--include-clingen-erepo` and `--clingen-erepo-local-file`.
- MCP tool: `query_clingen_erepo`.
- Report section: `ClinGen Evidence Repository Match`.

Future disease-specific rule-profile work should link to
`docs/VCEP_PROFILE_FRAMEWORK.md` when that framework exists. ERepo integration
does not activate VCEP profiles.
