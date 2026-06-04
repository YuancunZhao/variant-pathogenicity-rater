# Canonical Output Schema

Variant Pathogenicity Rater now emits an additive canonical output view for
single-variant, natural-language, batch, annotated-batch, CLI JSON, and MCP
rating outputs.

The canonical view is an output schema only. It does not change variant
normalization, provider retrieval, evidence generation, ACMG classification,
report rendering, or default offline/network behavior.

## Top-Level Canonical Sections

New clients should prefer these sections:

- `input`: original input, parsed input, inferred input type, and options used.
- `variant`: normalized variant, resolved variant, resolution summary,
  transcript validation, unresolved fields, and placeholder fields.
- `context`: disease, inheritance, gene-disease context, context used for
  rating, context consistency, confirmed context, and context candidates.
- `runtime`: legacy mock-mode flag, offline default posture, configured data
  source modes, unresolved placeholder state, network policy, and cache policy.
- `providers`: provider summary and normalized entries for ClinVar,
  population/gnomAD, computational/VEP, literature, ClinGen ERepo, transcript,
  and VCEP sources.
- `evidence`: applied, candidate, review-note, reviewed, and all evidence
  items, plus a descriptive evidence-status summary.
- `classification`: final classification, applied combination rule, confidence,
  full classification result, and whether curator-reviewed applied evidence was
  present.
- `review`: human-review requirement, review flags, review questions, and
  blocking reasons surfaced for review.
- `report`: report text, language, mode, and report sections.
- `provenance`: run id, timestamp, software version, parser versions,
  data-source versions, cache directory, and existing provenance details.
- `warnings`: non-fatal warnings collected for client display.
- `compatibility`: legacy fields and their canonical replacements.

## Provider Entry Shape

Each canonical provider entry uses the same field names:

- `requested_mode`
- `configured_mode`
- `attempted`
- `outcome`
- `records_count`
- `source_version`
- `query`
- `endpoint`
- `cache_hit`
- `limitations`
- `provenance`

`providers.summary` is the canonical replacement for the legacy
`provider_mode_summary` field. The legacy field remains emitted unchanged for
compatibility.

## Evidence Status Summary

`evidence.evidence_status_summary` is descriptive. It is not an input to the
ACMG combiner and must not be used to promote candidate evidence.

Statuses:

- `applied`
- `candidate_only`
- `review_note`
- `reviewed_applied`
- `reviewed_rejected`
- `needs_more_info`

Candidate and review-note evidence remain outside classification unless a
curator supplies valid `reviewed_applied` evidence through the existing manual
reviewed-evidence workflow.

## Compatibility Fields

The following legacy fields remain available and should not be removed or
renamed in the 77A compatibility period:

- `mock_mode`
- `offline_default_mode`
- `data_source_modes`
- `data_source_modes_semantics`
- `provider_mode_summary`
- `unresolved_placeholder_mode`
- `normalized_variant`
- `resolved_variant`
- `variant_resolution`
- `variant_resolution_summary`
- `transcript_validation`
- `evidence_items`
- `applied_evidence`
- `candidate_evidence`
- `review_note_evidence`
- `reviewed_evidence`
- `classification_result`
- `final_classification`
- `human_review_required`
- `human_review`
- `review_flags`
- `limitations`
- `report_text`
- `report`
- `step_results`

The raw `step_results` payload is intentionally not migrated in 77A. It remains
the existing raw step audit payload for compatibility and debugging.

## Client Guidance

Use canonical fields for new integrations:

- `variant.normalized` instead of `normalized_variant`.
- `variant.resolved` instead of `resolved_variant`.
- `variant.resolution_summary` instead of `variant_resolution`.
- `runtime.data_source_modes_configured` instead of `data_source_modes`.
- `providers.summary` instead of `provider_mode_summary`.
- `evidence.applied` instead of `applied_evidence`.
- `evidence.review_note` instead of `review_note_evidence`.
- `classification.final_classification` instead of `final_classification`.
- `review.review_flags` instead of `review_flags`.
- `report.report_text` instead of `report_text`.

CLI JSON and MCP tool outputs expose the same canonical sections because they
return the shared Python pipeline output.
