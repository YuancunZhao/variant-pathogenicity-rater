# Real Provider Validation Plan

This document defines the validation path for real provider behavior across
ClinVar, gnomAD-like population snapshots, MANE/RefSeq/Ensembl transcript
metadata, and ClinGen Evidence Repository. It is a validation and safety
hardening plan, not a plan to make online providers default behavior.

The validation goal is to prove that provider data is retrieved, parsed,
cached, matched, reported, and degraded safely. Concordance with external
assertions is not clinical correctness, and no provider result is allowed to
classify a variant by itself.

## Core Validation Rules

- Default provider mode remains offline `mock` or local-file.
- Local snapshots and fixtures are the primary validation path.
- Online checks are optional smoke tests only and require explicit opt-in.
- Default CI must not require ClinVar, gnomAD, MANE, Ensembl, RefSeq, or
  ClinGen network access.
- Provider failures, misses, stale data, malformed payloads, context mismatch,
  and missing provenance become limitations, review flags, or failed records.
- Provider records cannot override user-provided gene, disease, transcript,
  ancestry, inheritance, consequence, or genome build context.
- Provider-derived evidence cannot bypass generator safety gates.
- Provider-derived applied evidence remains review-required and must preserve
  provenance.
- External curated assertions from ClinVar and ClinGen ERepo remain
  candidate/review-note material unless a curator supplies valid
  `reviewed_applied` evidence through the manual reviewed-evidence workflow.
- The ACMG classification combiner must remain unchanged for provider
  validation.

## Implementation Roadmap

### Phase A: ClinVar Real Validation

ClinVar should be validated first because the project already has local-file
and opt-in online ClinVar support, and because ClinVar directly touches the
highest-risk external-assertion boundary for PS1/PM5 and PP5-style review
notes.

Required local fixture scenarios:

- Exact query variant with a ClinVar assertion.
- Comparator variant for PS1 with the same amino acid change and a different
  nucleotide or genomic change.
- Comparator variant for PM5 with the same residue and a different alternate
  amino acid.
- Pathogenic or likely pathogenic comparator that passes quality gates.
- Benign or likely benign assertion that remains review-note context only.
- Conflicting interpretation that blocks applied PS1/PM5.
- Low review status or insufficient review-star record.
- Somatic-only or otherwise non-germline-applicable record.
- Condition mismatch against the supplied disease context.
- Same-variant comparator that must block PS1.
- Missing or unparseable protein consequence.
- Transcript or protein accession mismatch.
- Missing provenance or source version.
- Malformed local record or malformed online-style payload.

Optional online smoke validation:

- Requires both explicit online mode and an explicit online-enabled gate.
- Must use a cache directory and record cache hit/miss behavior.
- Must assert source URL or endpoint, query metadata, retrieval timestamp, raw
  payload hash, parser version, source version or live-source label, and
  limitations.
- Must tolerate timeout, HTTP error, empty result, and malformed response by
  returning limitations rather than crashing the pipeline.
- Must remain excluded from default CI unless the required environment gates
  are present.

Acceptance checks:

- ClinVar review notes remain separate from applied evidence.
- ClinVar assertions never automatically trigger PP5 or BP6.
- PS1/PM5 can be emitted only through the comparator generator and only after
  protein, nucleotide, transcript/protein, condition, germline, conflict,
  quality, context, and provenance gates pass.
- Candidate-only ClinVar outputs use non-applied status and do not alter final
  classification.
- ClinVar provider misses are visible as limitations when relevant and do not
  imply absence from ClinVar.

### Phase B: gnomAD Local Snapshot Validation

gnomAD validation should begin with local JSONL snapshots that map into the
existing population-frequency schema. Online gnomAD integration should be
deferred until local parsing, provenance, no-record behavior, and quality gates
are validated.

Required local snapshot fields:

- Normalized variant key.
- Genome build.
- Dataset version or source version.
- Overall allele frequency.
- Maximum population allele frequency.
- FAF or filtering allele frequency when available.
- Allele count and allele number.
- Homozygote and hemizygote counts when available.
- Population and ancestry labels.
- Coverage quality or callable-region quality.
- Filters and low-confidence flags.
- Raw-record provenance, parser version, query metadata, retrieval timestamp,
  and raw-record hash.

Required validation scenarios:

- BA1-level high allele frequency with adequate context and quality.
- BS1-level allele frequency with adequate context and quality.
- True zero or very low frequency that can support only `PM2_Supporting` after
  rule gates pass.
- No local record found.
- Zero AF with insufficient allele number.
- Low coverage or non-callable region.
- Ancestry or population mismatch.
- Founder-population warning.
- Genome-build mismatch.
- Missing disease-specific threshold context.
- Missing source version.
- Stale snapshot version.
- Malformed AF, AC, AN, FAF, or filter fields.

Acceptance checks:

- The provider supplies normalized population facts only.
- `population_rules` remains the only path to applied BA1, BS1, or
  `PM2_Supporting`.
- No-record-found is limitation-only and never triggers PM2.
- Low AN, low coverage, ancestry mismatch, stale source, malformed fields, or
  genome-build mismatch block or downgrade evidence.
- Provider provenance is visible in outputs and reports.

Future online gnomAD behavior should be an opt-in mapper into the same
population-frequency schema. It should preserve dataset/build/version details,
cache raw payloads, and continue to delegate all evidence decisions to
`population_rules`.

### Phase C: MANE / RefSeq / Ensembl Transcript Metadata Validation

Transcript metadata validation should use local annotation fixtures first.
MANE, RefSeq, and Ensembl metadata are review context for transcript selection
and PVS1 review support; they do not generate ACMG evidence by themselves.

Required metadata:

- Transcript accession and version.
- Gene identifier and symbol.
- Consequence.
- Protein-coding status.
- MANE Select flag.
- Canonical flag.
- Exon number and exon count.
- Coding exon position.
- CDS and protein coordinates when available.
- NMD-relevant position or terminal-exon context when available.
- Source name, source version, genome build, parser version, query metadata,
  and raw-record provenance.

Required validation scenarios:

- User transcript matches an annotation record.
- User transcript is absent from annotation records.
- MANE Select is present and unambiguous.
- MANE Select is absent.
- Multiple MANE Select or canonical candidates exist.
- Canonical and MANE Select disagree.
- Protein-coding transcript is selected.
- Noncoding transcript is selected or is the only available candidate.
- Missing transcript identifier.
- Annotation sources disagree about gene, transcript, consequence, or tags.
- Exon count, exon position, and NMD metadata are available.
- Exon or NMD metadata is missing or malformed.

Acceptance checks:

- Transcript selection remains recommendation/review-note context only.
- A selected transcript does not apply PVS1, PP3, BP4, or any other criterion.
- Transcript metadata may support review of PVS1 transcript relevance, exon
  position, and NMD assumptions, but cannot substitute for disease mechanism,
  inheritance, consequence, or PVS1 safety gates.
- User-provided transcript context is not silently overridden.
- Ambiguity, mismatch, missing metadata, and source disagreement become review
  flags or limitations.

### Phase D: ClinGen Evidence Repository Online Validation

ClinGen Evidence Repository validation should preserve the current posture:
ERepo is a curated-source review-note and reviewed-draft support workflow, not
an automatic evidence or classification provider.

Required metadata:

- ClinGen Allele Registry CA ID when available.
- ClinVar Variation ID when available.
- Normalized genomic allele and HGVS identifiers.
- Gene and disease or condition.
- VCEP, expert panel, or curation group.
- Exact assertion, supporting summary, and criteria summaries when present.
- Citations and source links.
- Classification date, version, status, and reviewed/draft state.
- Source URL or API endpoint.
- Retrieval timestamp, cache key or payload hash, parser version, source
  version, and limitations.

Required validation scenarios:

- Exact variant match by CA ID.
- Exact variant match by ClinVar Variation ID.
- Exact variant match by normalized genomic allele.
- Transcript/HGVS match.
- Protein-only match.
- Gene-only match that produces only VCEP activity signal.
- Condition match and condition mismatch.
- Transcript match and transcript mismatch.
- Reviewed exact assertion.
- Draft, provisional, stale, or unversioned record.
- Supporting summary with citations.
- Supporting summary with missing citations.
- ClinVar/ERepo assertion conflict.
- Incomplete provenance.
- Online failure, timeout, empty response, and malformed response.

Acceptance checks:

- Exact variant matches remain review-note evidence, not applied evidence.
- Gene-level matches remain VCEP activity signals, not variant matches.
- Protein-only matches are candidate context and never exact matches.
- Supporting summaries may seed reviewed-evidence drafts only.
- Reviewed-evidence drafts default to `needs_more_info`.
- Drafts cannot affect classification unless a curator submits valid
  `reviewed_applied` evidence through the manual reviewed-evidence workflow.
- Stale, unversioned, conflicting, condition-mismatched, transcript-mismatched,
  or incomplete records become review flags or limitations.
- Online smoke is opt-in, cached, and excluded from default CI.

## Provider Validation Test Plan

Offline fixture tests are the release gate. Optional online tests are smoke
checks for provider reachability and parser resilience only.

Default offline tests should cover:

- Local fixture loading for ClinVar, population, transcript metadata, and ERepo
  records.
- Required provenance fields for each provider.
- Cache metadata where cache is used by the provider path under test.
- Malformed records and malformed provider payloads.
- Stale or missing source version.
- Genome-build mismatch.
- Gene, disease, condition, transcript, ancestry, and inheritance mismatch.
- Provider miss behavior.
- Candidate/applied separation.
- Report-visible limitations and review flags.
- Batch and annotated-batch preservation of per-record provider limitations
  where applicable.

Optional online smoke tests should be skipped unless provider-specific
environment gates are present. A smoke test may use provider-specific names, but
must require both a mode/config gate and an explicit online-enabled gate, for
example:

```bash
VPR_CLINVAR_MODE=online \
VPR_CLINVAR_ONLINE_ENABLED=true \
.venv/bin/python -m pytest tests/test_real_provider_online_smoke.py -m online
```

Online smoke acceptance:

- Network failure becomes a limitation.
- Timeout becomes a limitation.
- Cache hit and cache miss are distinguishable in provenance or provider
  metadata.
- Source endpoint, query, retrieval timestamp, parser version, source version
  or live-source label, and raw payload hash are preserved.
- Online provider output does not bypass local generator safety gates.
- Online provider output does not introduce CI nondeterminism.

## Safety Gates

Provider validation must preserve these safety gates:

- Online failure becomes a limitation and does not crash the interpretation
  workflow.
- Online or local provider data cannot bypass context, quality, provenance, or
  conflict gates.
- No provider directly changes final classification.
- ClinVar and ERepo assertions remain external curated-source review context,
  not automatic applied PP5/BP6 or direct ACMG criteria.
- gnomAD and population provider misses are not evidence of absence.
- MANE, RefSeq, and Ensembl transcript metadata cannot apply or upgrade PVS1 by
  themselves.
- All provider-derived evidence must pass through the existing generator or
  reviewed-evidence workflow.
- Applied evidence remains review-required.
- Provenance is required for provider-derived outputs.
- Missing provenance blocks or downgrades provider-derived evidence.
- The combiner remains isolated and unchanged.

## Risks

- Overcalling from external assertions, especially ClinVar P/LP records or
  ERepo exact matches.
- Treating a gnomAD no-record result as population absence.
- Letting transcript selection silently change PVS1 behavior.
- Hidden network dependency in CI or routine workflows.
- Stale snapshots appearing authoritative without source-version warnings.
- Provider context overriding user-provided gene, disease, transcript,
  ancestry, inheritance, consequence, or genome build.
- Cache reuse without visible provenance or source freshness.
- Real provider payload drift causing permissive parser fallbacks.
- Online smoke tests becoming treated as validation of clinical correctness.

## Deliverables

- `docs/REAL_PROVIDER_VALIDATION_PLAN.md`.
- ClinVar local fixture checklist covering exact variants, comparators,
  conflict, review status, condition, germline/somatic, malformed records, and
  provenance.
- gnomAD local snapshot checklist covering AF, FAF, AC, AN, ancestry, coverage,
  genome build, source version, no-record behavior, and malformed records.
- MANE/RefSeq/Ensembl transcript metadata checklist covering transcript
  selection, exon/NMD metadata, mismatch, ambiguity, and provenance.
- ClinGen ERepo checklist covering exact variant matches, gene-level VCEP
  signals, supporting summaries, drafts, stale/conflict handling, online cache,
  and provenance.
- Offline provider validation tests that do not require network access.
- Optional provider online smoke tests gated by explicit environment variables.
- Documentation of cache behavior, stale source behavior, malformed response
  behavior, and failure-to-limitation behavior.

## Recommended First Implementation Task

Start with Phase A: ClinVar real validation.

The first implementation task should not add new online behavior. It should add
or refine offline ClinVar validation fixtures and tests that prove:

- local snapshot provenance is complete
- malformed records degrade safely
- conflict, low review status, somatic-only status, condition mismatch, and
  missing provenance block applied PS1/PM5
- exact query variants are distinguished from comparator variants
- PS1 same-amino-acid comparators require a different nucleotide or genomic
  change
- PM5 comparators require the same residue and a different alternate amino
  acid
- ClinVar review notes do not leak into applied evidence
- optional online failure and cache behavior are tested only behind explicit
  gates

After ClinVar validation is complete, proceed to gnomAD local snapshot
validation, then transcript metadata validation, then opt-in ClinGen ERepo
online validation.
