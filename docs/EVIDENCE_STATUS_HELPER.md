# Evidence Status Helper

77C adds a shared read-only evidence status helper for grouping and displaying
evidence consistently across pipeline, canonical output, reports, reviewed
evidence read paths, and batch summaries.

The helper does not generate evidence, validate reviewed evidence, change the
classification combiner, alter `final_classification`, or promote candidate
evidence.

## Status View

`src/variant_pathogenicity_rater/evidence/status.py` defines:

- `EvidenceDisplayStatus`
- `EvidenceWorkflowStatus`
- `EvidenceStatusView`

`EvidenceStatusView` exposes:

- `evidence_id`
- `code`
- `strength`
- `direction`
- `applied`
- `candidate_only`
- `requires_review`
- `is_applied`
- `is_candidate`
- `is_review_note`
- `is_reviewed`
- `reviewed_status`
- `display_status`
- `combiner_eligible`
- `reason`
- `source_name`
- `provenance_summary`
- `limitations`

## Helper Functions

- `build_evidence_status_view(item)`
- `is_applied_evidence(item)`
- `is_candidate_evidence(item)`
- `is_review_note_evidence(item)`
- `is_combiner_eligible(item)`
- `summarize_evidence_status(items, reviewed_records=None)`
- `split_evidence_by_status(items, reviewed_records=None)`

The helpers accept `EvidenceItem` instances and dict-like evidence records.
They can read reviewed evidence records, literature suggestions, and ERepo
draft records for display/status summaries.

## Safety Rules

- `candidate_only=true` is not combiner eligible.
- `applied=false` is not combiner eligible.
- `strength=none` is not combiner eligible.
- `supporting_data.candidate_only=true` is not combiner eligible.
- `supporting_data.applied=false` is not combiner eligible.
- `supporting_data.evidence_status=candidate` is not combiner eligible.
- Raw `reviewed_applied` records are not combiner eligible until the existing
  reviewed evidence workflow converts them into applied `EvidenceItem`
  objects.
- `reviewed_rejected`, `needs_more_info`, and invalid reviewed records are not
  combiner eligible.
- ClinVar, ClinGen ERepo, and literature suggestions remain review-note or
  candidate-only unless converted through valid reviewed evidence.

## Canonical Summary

`evidence.evidence_status_summary` now uses the shared helper and includes:

- `applied_count`
- `candidate_count`
- `review_note_count`
- `reviewed_applied_count`
- `reviewed_rejected_count`
- `needs_more_info_count`
- `invalid_count`
- `combiner_eligible_count`
- `codes_by_status`

Legacy count keys such as `applied`, `candidate_only`, `review_note`,
`reviewed_applied`, `reviewed_rejected`, and `needs_more_info` remain present.
