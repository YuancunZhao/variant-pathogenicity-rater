# ClinVar Real Provider Validation

This document records the validation contract for `64_clinvar_real_provider_validation`.
The goal is to prove ClinVar provider parsing and safety behavior with local
fixtures first. It is not a plan to make ClinVar online behavior default.

## Safety Boundaries

- ClinVar assertions are review-note or comparator context only.
- ClinVar must not directly apply `PP5` or `BP6`.
- ClinVar comparator records may affect classification only through the
  existing PS1/PM5 comparator gates or through a separate reviewed-evidence
  workflow.
- The ACMG classification combiner is not changed for ClinVar validation.
- Provider failures, malformed records, missing records, source conflicts, and
  incomplete provenance become limitations or review flags.
- Online ClinVar smoke tests are opt-in and skipped by default.

## Local Fixture

The offline validation fixture is:

```text
data/fixtures/clinvar_real_provider_validation.jsonl
```

Each record has a stable `case_id` and preserves the ClinVar fields needed by
the parser, review-note mapper, PS1/PM5 comparator workflow, and reporting.

Fixture scenarios:

- `expert_panel_plp`: high-confidence germline P/LP review-note record.
- `multiple_submitter_plp`: moderate-confidence germline P/LP review-note
  record.
- `single_submitter_plp`: low-confidence germline P/LP review note.
- `conflicting_interpretation`: conflicting ClinVar assertion that blocks
  applied PS1/PM5.
- `benign_likely_benign`: B/LB assertion that remains candidate BP6-style
  review context only.
- `somatic_only`: somatic-only record that is not used as germline ACMG
  candidate evidence.
- `missing_protein`: P/LP comparator with no protein consequence, forcing
  PS1/PM5 downgrade/block behavior.
- `condition_mismatch`: otherwise plausible comparator that fails disease
  condition matching.
- `exact_same_variant`: same nucleotide/genomic variant, which blocks PS1/PM5.
- `ps1_comparator`: same amino acid change with a different nucleotide/genomic
  allele for PS1 gate validation.
- `pm5_comparator`: same residue with a different alternate amino acid for PM5
  gate validation.

## Required Parsed Fields

Validation asserts the provider preserves:

- Variation ID.
- Clinical significance.
- Review status, review-star level, and review confidence.
- Condition and condition list.
- Germline/somatic applicability.
- HGVS c. and p. values.
- Transcript and protein accession context.
- Gene symbol.
- Genomic allele: build, chromosome, position, reference, alternate.
- Citations.
- Last evaluated date.
- Submitter count.
- Provenance: source version, parser version, query, retrieval timestamp, raw
  record hash, source URL or endpoint when present.

## Offline Test Coverage

Default pytest and CI use local fixtures and mocked provider payloads only.

Offline tests cover:

- Local-file provider fixture parsing and provenance.
- Candidate-only ClinVar review-note mapping for P/LP and B/LB records.
- Low-confidence review status handling.
- Conflicting-interpretation review flags.
- Somatic-only filtering.
- Malformed local records returning limitations instead of crashing the
  provider or pipeline.
- PS1 and PM5 application only through comparator gates.
- Blocking for condition mismatch, same variant, missing protein, conflict,
  low quality, and non-germline applicability.
- Report separation between Applied ACMG Evidence and Candidate / Review-Note
  Evidence.
- MCP and CLI behavior with offline/default sources.
- ClinVar/ERepo conflict review flags without classification changes.

## Optional Online Smoke

Live ClinVar smoke validation is skipped unless all gates are set:

```bash
VPR_CLINVAR_ONLINE_SMOKE=true
VPR_CLINVAR_MODE=online
VPR_CLINVAR_ONLINE_ENABLED=true
```

Supported online smoke settings:

```bash
VPR_CLINVAR_TIMEOUT_SECONDS=5
VPR_CLINVAR_CACHE_DIR=.cache/variant_pathogenicity_rater/clinvar
VPR_CLINVAR_EMAIL=curator@example.org
VPR_CLINVAR_USER_AGENT="variant-pathogenicity-rater validation"
```

The smoke test checks parser resilience and provenance, not clinical
correctness. It must tolerate empty results, timeout, HTTP errors, cache hits,
and malformed responses by returning limitations instead of crashing.

## Expected Limitations And Flags

Expected limitations include:

- ClinVar local-file mode is candidate-only.
- No local record matched the supplied query.
- Malformed local record could not be indexed or parsed.
- ClinVar online query failed.
- Somatic-only ClinVar records were not used as germline ACMG candidates.
- PS1/PM5 comparator gates were insufficient or blocked.

Expected review flags include:

- `CLINVAR_CONFLICTING_INTERPRETATIONS`
- `CLINVAR_LOW_REVIEW_CONFIDENCE`
- `CLINVAR_NON_GERMLINE_ASSERTION`
- `CLINVAR_CONDITION_MISMATCH`
- `PS1_PM5_REQUIRES_REVIEW`
- `PS1_PM5_CLINVAR_CONFLICT`
- `PS1_PM5_CONDITION_MISMATCH`
- `CLINGEN_EREPO_CLINVAR_CONFLICT`

## Acceptance Criteria

- Default `pytest` does not require network access.
- Online smoke is opt-in only.
- Provider failure becomes a limitation.
- ClinVar review notes stay outside applied evidence.
- ClinVar never directly applies `PP5` or `BP6`.
- Applied PS1/PM5 can appear only after comparator gates pass and remains
  review-required.
- ClinVar/ERepo conflicts are visible review flags and do not alter the final
  classification by themselves.
