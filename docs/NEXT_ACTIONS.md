# Next Actions

This file lists the highest-value next tasks for the current project state.
Before starting any task, read `docs/PROJECT_STATE.md`,
`docs/ROADMAP_CURRENT.md`, `docs/KNOWN_LIMITATIONS.md`, and
`docs/APPLIED_EVIDENCE_GENERATION.md`. For the current applied evidence status
review, also read `docs/APPLIED_EVIDENCE_STATUS.md`.

## Recommended Next Task

The recommended next task is `54_vcep_clingen_rule_knowledge_base`.

It is the best next step because the post-v0.2.0-beta interpretation loop is
now complete: automatic applied evidence generation exists for PVS1,
population, computational, and ClinVar-derived PS1/PM5 evidence; candidate and
literature suggestions are retained for review; manual reviewed evidence can
explicitly supply curator-approved applied evidence; ClinGen ERepo integration
now provides gene-level VCEP signals, exact-match review notes, supporting
summaries, and reviewed-evidence drafts; and the combiner remains unchanged.
The next constraint is rule knowledge: disease/gene-specific VCEP or ClinGen
guidance must be versioned, explicitly selected, provenance-backed, and
validated before the system broadens beyond generic ACMG support.

## Prioritized Task List

| Task name | Priority | Short summary | Risk level | Expected modules touched | Combiner must remain untouched |
| --- | --- | --- | --- | --- | --- |
| `54_vcep_clingen_rule_knowledge_base` | P0 | Design and implement explicit versioned VCEP/ClinGen rule knowledge with profile selection and mismatch safety gates. | High | Profile docs/config schemas, evidence generator inputs, reports, tests | Yes unless a separate impact review is approved |
| `56_real_provider_validation_clinvar_gnomad_mane_erepo` | P0 | Validate ClinVar, gnomAD, MANE, and ERepo online provider behavior with provenance, local fixtures or opt-in online mode, and failure-to-limitation checks. | High | Provider adapters/fixtures, validation docs, smoke tests, provenance reports | Yes |
| `55_benchmark_expansion` | P1 | Expand the offline benchmark beyond 21 curated cases with rationale, expected applied/candidate/reviewed evidence, literature drafts, and safety checks. | Medium | Data fixtures, benchmark docs, benchmark tests | Yes |
| `57_chinese_report_template` | P1 | Add Chinese report output while preserving human-review-required language, VUS caution, provenance, applied/candidate separation, and reviewed-evidence labeling. | Medium | Reporting templates, docs, report tests | Yes |
| `61_disease_specific_profile_pilot` | P1 | Add one narrow disease-specific profile only after the rule knowledge base is versioned and explicit profile activation is available. | High | Profile config, evidence generator inputs, reports, benchmark cases | Yes unless a separate impact review is approved |
| `clingen_erepo_integration_validation` | Done | Validated ClinGen ERepo as a conservative curated-source review-note and reviewed-draft integration with no automatic application. | High | ERepo provider, reviewed drafts, reports, CLI/MCP, docs, tests | Yes |
| `52_manual_reviewed_evidence_workflow` | Done | Implemented explicit curator-reviewed evidence input with strict validation, provenance, batch/CLI/MCP support, and no silent candidate promotion. | High | Input schemas, validation, provenance, reports, batch, CLI, MCP, docs, tests | Yes |
| `53_literature_suggested_evidence_review_workflow` | Done | Implemented literature suggested-evidence to reviewed-draft workflow; drafts default to needs-more-info and require curator edits before reviewed_applied use. | High | Literature agent, suggestion schemas, reviewed draft tool, CLI/MCP, reports, docs, tests | Yes |
| `51_clinvar_and_ps1_pm5_generation` | Done | Implemented conservative ClinVar-derived PS1/PM5 applied generator with candidate-only fallbacks and no PP5/BP6 reuse. | Medium-high | ClinVar comparator workflow, reports, CLI/MCP serialization, docs, focused tests | Yes |
| `legacy_vcep_profile_design` | Superseded by `54_vcep_clingen_rule_knowledge_base` | Design explicit disease/gene-specific VCEP profile configuration before implementation. | High | Design docs, schema proposal, roadmap docs | Yes for design; any later implementation needs explicit impact review |
| `58_release_review_standardization` | P2 | Convert release review into a repeatable checklist-driven gate tied to docs, benchmarks, smoke, provenance, and leakage checks. | Low-medium | Docs, release notes template, optional scripts later | Yes |
| `59_provider_provenance_audit` | P3 | Audit all provider outputs for source version, query, snapshot, timestamps, limitations, and offline/online mode labels. | Medium | Provider adapters, schemas, reports, docs, tests | Yes |
| `60_batch_report_consistency_audit` | P3 | Verify single, batch, annotated-batch, CLI, and MCP outputs preserve the same evidence separation and safety language. | Medium | Batch orchestration, reports, CLI/MCP output tests, docs | Yes |

## Guardrails For Selecting Work

Prefer tasks that strengthen safety, reviewability, provenance, and validation.
Avoid tasks that broaden variant scope or automate strong evidence without the
required clinical context.

Do not start CNV/SV, repeat, mitochondrial, methylation, trio/family-aware,
wet-lab/RNA, or clinical sign-out tasks as implementation work in the current
stage. Those belong in design or future validated tracks.
