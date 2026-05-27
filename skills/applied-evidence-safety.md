# Applied Evidence Safety Skill

Use this skill for any task that touches ACMG evidence, providers, reports,
batch outputs, CLI/MCP outputs, literature suggestions, ClinVar review notes,
or classification behavior.

This is the core safety-boundary skill for Variant Pathogenicity Rater.

## Non-Negotiable Boundary

Candidate-only evidence must not leak into the classification combiner.

Candidate and review-note evidence may be displayed, summarized, exported,
benchmarked, and used to guide human review. It must not be counted as applied
ACMG evidence unless a separate explicitly reviewed workflow validates and
promotes it under documented gates.

## Prohibited Automatic Evidence

Future tasks must not introduce:

- Automatic `PS3`.
- Automatic `BS3`.
- Automatic `PS2`.
- Automatic `PM6`.
- Automatic `PP1`.
- Automatic `PS4`.
- Automatic `PP4`.
- Automatic `PM3`.
- Automatic applied literature evidence.
- Automatic applied ClinVar assertion reuse.
- Automatic applied ClinGen ERepo assertion or VCEP-criteria reuse.
- Automatic clinical sign-out.

These evidence types require manual review and often require assay validity,
parentage, trio/family data, segregation counts, cohort design, phenotype
specificity, disease mechanism, or deduplication that the current system cannot
autonomously validate.

They may be counted only when supplied through the reviewed-evidence workflow as
valid `reviewed_applied` records with explicit curator decision, rationale,
provenance, and audit trail.

## Literature Safety

Literature evidence must remain review-required. Literature extraction can
surface candidate suggestions, citations, extracted claims, limitations, and
review questions. It must not by itself create applied ACMG evidence.

Ambiguous paper language should become a limitation or review question.
Duplicate families, overlapping cohorts, unmatched disease context, unmatched
transcripts, and unclear assay validity must block automatic promotion.

## External Curated Source Safety

ClinVar and ClinGen ERepo are external curated sources for review support.
ClinVar review notes, ERepo exact variant matches, ERepo gene-level VCEP
signals, ERepo supporting summaries, and reviewed-evidence drafts must not
automatically classify variants.

ERepo supporting summaries may seed reviewed-evidence drafts. Drafts default to
non-applied review status and require explicit curator action before any
criterion can enter the combiner.

## VCEP Signal And Override Safety

The VCEP signal/override framework is implemented and validated as a
lightweight local profile layer, not a full VCEP reasoning engine.

VCEP gene-level signals, draft/provisional profiles, deprecated profiles,
conflicting profiles, and profile limitations are review context. Signal
presence alone must not change evidence strength or classification.

Approved profile overrides require explicit runtime enablement, an approved
non-conflicting profile, applicable context, and retained provenance. Overrides
may adjust only the documented safe generator parameters or downgrade generated
criteria before classification. They must not create evidence, promote
candidate evidence, bypass generator safety gates, or change the combiner.

Disabled criteria must become candidate/review-note evidence with review flags
and `supporting_data.vcep_override`; they must not be silently deleted. Batch
and annotated-batch workflows must preserve per-record `vcep_profile_summary`
when VCEP profile context is present.

## Computational Safety

Computational prediction is not functional evidence.

SpliceAI and similar tools are computational splice predictors. SpliceAI is not
RNA validation, not wet-lab validation, not `PS3`, not `BS3`, and not `PVS1` by
itself. It must not upgrade PVS1 or be represented as functional assay evidence.

`PP3` and `BP4` remain supporting-only and review-required. Predictor conflict,
single-predictor support, inappropriate consequence, transcript mismatch, genome
build mismatch, or missing calibration must block applied computational
evidence.

## Review Requirement

All applied evidence requires human review. This applies to:

- Machine-generated `PVS1`.
- Machine-generated `BA1`.
- Machine-generated `BS1`.
- Machine-generated `PM2_Supporting`.
- Machine-generated `PP3`.
- Machine-generated `BP4`.
- Machine-generated `PS1`.
- Machine-generated `PM5`.
- Any future reviewed-evidence workflow.

Report, CLI, MCP, batch, and annotated-batch outputs must preserve this
review-required posture.

## Provider And Provenance Safety

All online providers must preserve provenance and default to off. Online
features require explicit opt-in and must degrade to limitations when retrieval
fails, times out, returns mismatched context, or lacks source/version metadata.

Provider records cannot automatically override user-provided context. Mismatched
gene, transcript, condition, ancestry, genome build, consequence, or inheritance
must be surfaced as review flags or limitations.

## Future Task Checklist

For any future task touching evidence behavior, verify:

- Candidate-only evidence stays out of the combiner.
- Applied evidence remains review-required.
- Reports keep applied and candidate evidence separate.
- CLI, MCP, batch, and annotated-batch outputs are consistent.
- Provenance is preserved.
- VCEP override provenance and report visibility are preserved when applicable.
- VCEP signals, provisional/draft profiles, deprecated profiles, and profile
  conflicts do not alter classification.
- Failures become limitations or structured failed records.
- Online behavior remains opt-in.
- Tests cover leakage and safety boundaries.

If a proposed change weakens any of these rules, stop and redesign the change
before editing.
