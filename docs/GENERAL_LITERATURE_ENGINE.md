# General Literature Search and Summary Engine

The general literature engine expands the existing ACMG Literature Evidence
Agent into a citation-preserving search, normalization, deduplication, and
criterion-summary workflow.

It is decision support only. It does not modify the classification combiner,
does not create applied literature evidence, and does not change final
classification. All literature-derived `EvidenceItem`-like outputs are emitted
with `candidate_only: true`, `applied: false`, `strength: none`, and
`requires_review: true`.

## Inputs

Python, CLI, and MCP entry points accept:

- `gene`
- `variant`
- `transcript`
- `disease`
- `inheritance`
- `phenotype`
- `criteria`
- `literature_records`
- `pmids`
- `search_query`
- `variant_aliases`
- `use_online_pubmed`
- `use_online_litvar`

`literature_records` may come from local fixtures, curated snapshots, Codex, or
Life Science Research workflows. Codex and Life Science Research records are
treated as caller-supplied extraction records, not trusted clinical evidence.

## Record Schema

Normalized records preserve:

- PMID
- DOI
- title
- abstract
- optional full-text excerpt
- source
- retrieval timestamp
- query
- matched gene, variant, disease, and transcript
- variant and disease match levels
- study type
- evidence domains
- extracted claims
- citations
- provenance

Malformed records become limitations and review flags. They do not abort the
whole workflow.

## Search Strategy

The query builder creates deterministic query plans for:

- exact variant aliases
- gene + disease
- gene + protein consequence
- gene + criterion-specific keywords
- PubMed-style templates
- LitVar-style templates
- PMID direct lookup

The default runtime is offline and uses only supplied or local records. Online
PubMed and LitVar are opt-in. The current local implementation records opt-in
requests and degrades safely to limitations when online retrieval is not
performed.

## Criterion Summaries

The engine summarizes review-only candidate support for:

- PS3/BS3 functional assays
- PS2/PM6 de novo reports
- PP1 segregation
- PS4 case-control, enrichment, or unrelated-case evidence
- PM3 trans compound heterozygous observations
- PP4 phenotype specificity
- PS1/PM5 same amino acid or same-residue missense support
- PM1 hotspot or critical-domain support
- PVS1 LoF, NMD, and disease-mechanism support

PVS1 literature summaries are mechanism support only. They do not run or
override PVS1 scoring.

## Output

`search_and_summarize_literature` returns:

- `literature_search_results`
- `literature_summary`
- `criterion_summaries`
- `literature_evidence_assessments`
- `suggested_evidence`
- `evidence_items`
- `review_questions`
- `blocking_flags`
- `review_flags`
- `duplicate_groups`
- `limitations`
- `reviewed_evidence_drafts`
- `reviewed_evidence`
- `query_plan`
- `citations`
- `provenance`

`reviewed_evidence_drafts` default to `evidence_status: needs_more_info` and
must be curated before any evidence can be supplied as `reviewed_applied`.

## Safety Gates

- Variant mismatch creates a blocking flag.
- Disease mismatch creates a blocking flag.
- Abstract-only records create limitations/review flags.
- Duplicate publications, cases, cohorts, and families are collapsed before
  criterion summaries.
- Low extraction confidence creates review flags.
- AI/Codex extracted claims require manual review.
- Suggested strengths are reviewer guidance only.
- No literature output changes classification.

## CLI

```bash
vpr literature-search \
  --gene GENE1 \
  --variant NM_000001.1:c.76A\>G \
  --disease "GENE1 disorder" \
  --literature-records records.json
```

Use `--online-pubmed` or `--online-litvar` only for explicit online opt-in.
Offline/local validation does not depend on network access.

## MCP

Use `search_and_summarize_literature` for the full search and summary workflow.
Use `create_reviewed_evidence_draft` only to convert suggested output into
manual draft templates.
