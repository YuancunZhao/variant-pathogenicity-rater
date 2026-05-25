# Context Consistency Checks

Context consistency checks validate that the variant, gene, transcript,
disease, inheritance, annotation records, and provider records describe the same
interpretation context.

They are safety checks only. They are not ACMG evidence, do not add ACMG rules,
and do not participate in the classification combiner.

## What Is Checked

The checker currently reviews:

- User/input gene versus annotation gene.
- User/input transcript versus annotation transcript.
- Selected transcript versus normalized variant transcript.
- ClinVar condition versus user disease.
- Population ancestry/context versus user disease ancestry.
- Missing or disease-inconsistent inheritance.
- HGVS c. transcript prefix versus the transcript field.
- Protein HGVS entries that lack enough gene/transcript context.
- Annotation consequence versus normalized variant type.
- Multiple genes or transcripts across annotation records.
- Provider genome build versus input genome build.
- Missing disease context when population records are available.

## Output Contract

`ContextConsistency` includes:

- `status`: `ok`, `warning`, `conflict`, or `insufficient`.
- `checks`: all check objects.
- `conflicts`: checks with conflict severity.
- `warnings`: warning and insufficient-context checks.
- `limitations`: limitations to carry into the report.
- `review_required`: true unless status is `ok`.
- `provenance`: checker version, timestamp, and input counts.

Each check includes:

- `check_name`
- `severity`
- `field`
- `expected`
- `observed`
- `reason`
- `source`
- `requires_review`

## Required Manual Review

Manual review is required for any `conflict`, including:

- Gene mismatch between user input and annotation.
- Transcript mismatch between user input, selected transcript, and annotation.
- HGVS transcript prefix mismatch.
- ClinVar condition mismatch with the requested disease context.
- Provider genome build mismatch.
- Multiple annotation genes.
- Provider-marked population ancestry mismatch.
- Inheritance that conflicts with disease wording.

`insufficient` status also requires review before confidence is elevated from
missing context.

## Safety Behavior

Context consistency does not directly alter the ACMG evidence list and does not
reclassify a variant. Instead it adds review flags, limitations, and a report
section.

Provider records cannot silently override user input because provider context may
come from a different transcript, disease assertion, genome build, ancestry, or
snapshot. Conflicting context must be resolved by a qualified reviewer or by
rerunning the workflow with corrected input.

When disease context is missing, population and PVS1-related confidence must not
be elevated. Population rules remain candidate-only under missing disease,
inheritance, penetrance, or disease-specific-threshold context. PVS1 is not
applied without disease context even when a loss-of-function consequence is
present.

## Pipeline Integration

`rate_variant` runs `evaluate_context_consistency` after provider retrieval and
before report rendering. The result is returned as:

- top-level `context_consistency`
- top-level `consistency_warnings`
- `classification_result.context_consistency`
- report `summary.context_consistency`
- batch `context_consistency_summary` per successful record
- annotated-batch `context_consistency_summary` per successful record

MCP and CLI JSON outputs include the same fields because they return the pipeline
payload. Markdown reports include a `Context Consistency` section.
Context consistency can add review flags and limitations, but it is not included
in `applied_evidence` and cannot change `final_classification`.
