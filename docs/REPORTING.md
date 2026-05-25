# Reporting

Variant reports are presentation artifacts over an existing `ClassificationResult`.
The report renderer does not add ACMG criteria, change evidence strength, rerun
the classification combiner, or relax safety rules.

## Report Sections

Text reports in `concise`, `detailed`, `laboratory`, and `clinician` modes use the
same safety-oriented section model:

- `Executive Summary`: final machine proposal, evidence counts, and human review
  requirement.
- `Variant Summary`: normalized variant identity and submitted transcript/HGVS
  context.
- `Final Classification`: the supplied machine proposal and combination rule.
- `Why This Classification`: a short explanation of the supplied classifier
  output, without recomputation.
- `Transcript Selection`: recommendation/review-note context only. This is not
  ACMG evidence and is not counted by the classification combiner.
- `Context Consistency`: mismatch, warning, or insufficient-context status only.
  Context conflicts require review but do not directly change the classification.
- `Applied ACMG Evidence`: the only section that lists evidence treated as
  applied in the supplied classification result.
- `Candidate / Review-Note Evidence`: ClinVar, literature, and other candidate
  items that require manual evaluation and were not counted by the combiner.
- `Conflicting Evidence`: supplied conflict summaries and prominent ClinVar
  conflict warnings.
- `Limitations`: limitations carried from pipeline and providers.
- `What Data May Be Missing`: renderer-generated missing-data notes, such as no
  context consistency or transcript selection summary.
- `Data Sources / Provenance`: evidence source names, versions, retrieval
  timestamps, query details, and raw snapshot references where available.
- `Safety Notes`: conservative interpretation notes and the mandatory human
  review statement.

## Output Formats

- `markdown`: sectioned report intended for review and audit.
- `plain_text`: markdown headings are flattened for systems that do not render
  markdown.
- `json`: stable top-level keys for downstream tools:
  `executive_summary`, `variant`, `final_classification`,
  `why_this_classification`, `applied_evidence`, `review_note_evidence`,
  `context_consistency`, `transcript_selection`, `data_sources`, `limitations`,
  `missing_data`, `safety_notes`, `review_flags`, and `human_review_required`.

The legacy JSON keys `evidence`, `data_source_summary`, `cautions`,
`clinvar_conflict_detected`, and `human_review_note` remain present for
compatibility.

## Safety Wording

- VUS wording is conservative: a VUS is not described as leaning pathogenic or
  benign.
- Candidate evidence is always labeled as candidate/review-note only.
- ClinVar and literature assertions are not reported as applied evidence unless
  they already appear as applied evidence in the supplied classification result.
- SpliceAI is described as computational splice prediction only, not functional
  evidence.
- Transcript selection and context consistency are review context, not ACMG
  evidence.
- A context conflict is review-required context and is not a classification
  change.
- Every report states that qualified human review is required before clinical or
  laboratory use.

## Batch Summary

Batch results include both per-record outputs and a stable `summary` object:

- `total_records`
- `succeeded`
- `failed`
- `classification_distribution`
- `review_required_count`
- `conflict_count`
- `failed_records_summary`
- `duplicate_warnings`

The batch summary is for triage and audit only. It does not override per-record
classification, review flags, limitations, or human review requirements.
