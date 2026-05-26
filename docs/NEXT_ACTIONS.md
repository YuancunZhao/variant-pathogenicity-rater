# Next Actions

This file lists the highest-value next tasks for the current project state.
Before starting any task, read `docs/PROJECT_STATE.md`,
`docs/ROADMAP_CURRENT.md`, `docs/KNOWN_LIMITATIONS.md`, and
`docs/APPLIED_EVIDENCE_GENERATION.md`. For the current applied evidence status
review, also read `docs/APPLIED_EVIDENCE_STATUS.md`.

## Recommended Next Task

The recommended next task is `52_manual_reviewed_evidence_workflow`.

It is the best next step because PS1/PM5 applied generation is now implemented,
while literature, segregation, functional, case-count, PM3, and phenotype
evidence remain candidate suggestions or unsupported for automatic applied
evidence. A manual reviewed evidence workflow is the needed safety bridge for
explicitly human-reviewed evidence to enter classification without silently
promoting machine suggestions. The classification combiner should remain
unchanged.

## Prioritized Task List

| Task name | Priority | Short summary | Risk level | Expected modules touched | Combiner must remain untouched |
| --- | --- | --- | --- | --- | --- |
| `52_manual_reviewed_evidence_workflow` | P0 | Allow explicitly human-reviewed evidence input while keeping it distinct from machine candidate suggestions. | High | Input schemas, validation, provenance, reports, batch, CLI, MCP, docs, tests | Yes, unless an explicit combiner review proves no logic change |
| `53_literature_suggested_evidence_review_workflow` | P1 | Improve literature suggestion structure, deduplication, limitations, and review workflow for PS3/BS3, PS2/PM6, PP1/PS4/PP4, PM3, and PS1/PM5-related claims while keeping suggestions candidate-only by default. | High | Literature agent, suggestion schemas, reports, docs, tests | Yes |
| `54_vcep_profile_framework` | P1 | Design and implement explicit disease/gene-specific profile selection, version provenance, and profile mismatch safety gates. | High | Profile docs/config schemas, evidence generator inputs, reports, tests | Yes unless a separate impact review is approved |
| `55_benchmark_expansion` | P1 | Expand the offline benchmark beyond 21 curated cases with rationale, expected applied/candidate evidence, and safety checks. | Medium | Data fixtures, benchmark docs, benchmark tests | Yes |
| `51_clinvar_and_ps1_pm5_generation` | Done | Implemented conservative ClinVar-derived PS1/PM5 applied generator with candidate-only fallbacks and no PP5/BP6 reuse. | Medium-high | ClinVar comparator workflow, reports, CLI/MCP serialization, docs, focused tests | Yes |
| `56_real_world_validation_expansion` | P1 | Expand offline real-data smoke coverage beyond 10 cases using local fixtures and conservative allowed outcomes. | Medium | Smoke fixtures, smoke docs, smoke tests, report snapshots if present | Yes |
| `57_chinese_report_template` | P2 | Add Chinese report output while preserving human-review-required language, VUS caution, provenance, and applied/candidate separation. | Medium | Reporting templates, docs, report tests | Yes |
| `legacy_vcep_profile_design` | Superseded by `54_vcep_profile_framework` | Design explicit disease/gene-specific VCEP profile configuration before implementation. | High | Design docs, schema proposal, roadmap docs | Yes for design; any later implementation needs explicit impact review |
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
