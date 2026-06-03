# Next Actions

This file lists the highest-value next tasks for the current project state.
Before starting any task, read `docs/PROJECT_STATE.md`,
`docs/ROADMAP_CURRENT.md`, `docs/KNOWN_LIMITATIONS.md`, and
`docs/APPLIED_EVIDENCE_GENERATION.md`. For the current applied evidence status
review, also read `docs/APPLIED_EVIDENCE_STATUS.md`.

## Recommended Next Task

The recommended next task is `63_selected_real_world_case_validation`.

It is the best next step because benchmark Phase C, Chinese report output, the
offline Variant Resolution Framework, and real resolution provider validation
are implemented. The current
interpretation loop now preserves normalization, resolution, evidence,
classification, and reporting boundaries, so the highest-value next work is
selected real-world case validation using local fixtures/snapshots and
explicit provenance.

The next constraint is real-world review confidence rather than adding another
automatic evidence rule. Selected cases should exercise transcript resolution,
provider gaps, ClinVar comparator ambiguity, ERepo review notes, and report
wording without changing evidence logic or the combiner.

## Prioritized Task List

| Task name | Priority | Short summary | Risk level | Expected modules touched | Combiner must remain untouched |
| --- | --- | --- | --- | --- | --- |
| `63_selected_real_world_case_validation` | P0 | Validate selected real-world SNV/small-indel cases with completed provider boundaries, provenance review, and no direct provider classification. | High | Case fixtures, validation docs, report examples | Yes |
| `61_selected_real_vcep_profile_pilot` | P1 | Pilot one selected real VCEP profile only after toy profile, real provider validation, and benchmark Phase C pass. | High | Profile config, provenance docs, reports, benchmark cases | Yes |
| `64_optional_online_smoke_gates` | P2 | Add explicitly gated online smoke checks for provider reachability, cache/provenance, parser resilience, and failure-to-limitation behavior. | Medium | Provider smoke tests, docs, optional CI docs | Yes |
| `69_real_resolution_provider_validation` | Done | Validated offline real-resolution provider snapshots for HGVS c. to transcript, protein consequence, coordinate, exon, and NMD context, with mismatch flags and no evidence generation. | High | Resolution fixtures, safety flags, validation docs, tests | Yes |
| `65_variant_resolution_framework` | Done | Added an offline fixture-backed Variant Resolution Layer for transcript, protein, coordinate, exon, and NMD context with CLI/MCP/report integration and no ACMG evidence generation. | High | Resolution fixtures, pipeline, CLI/MCP, reports, docs, tests | Yes |
| `57_chinese_report_template` | Done | Added Chinese report output while preserving human-review-required language, VUS caution, provenance, applied/candidate separation, and reviewed-evidence labeling. | Medium | Reporting templates, docs, report tests | Yes |
| `55_benchmark_expansion` | Done | Expanded the offline benchmark to 100 curated SNV/small-indel cases with fixture-backed providers, annotation/transcript fixtures, strict applied/candidate expectations, and Phase C safety coverage. | Medium | Data fixtures, benchmark docs, benchmark tests | Yes |
| `62_toy_vcep_profile_validation` | Done | Validated the completed VCEP signal/override framework with toy profiles, profile-off/profile-on examples, report provenance, and batch summaries. | High | Profile fixtures, validation docs, benchmark/report examples | Yes |
| `56_real_provider_validation_clinvar_gnomad_mane_erepo` | Done | Validated ClinVar, gnomAD, MANE, and ERepo provider behavior with local fixtures/snapshots, opt-in online boundaries, provenance, cache visibility, and failure-to-limitation checks. | High | Provider adapters/fixtures, validation docs, smoke tests, provenance reports | Yes |
| `54_vcep_clingen_rule_knowledge_base` | Done | Implemented lightweight versioned VCEP signal/override framework with explicit profile selection, safe override surface, provenance, reporting, and batch summaries. | High | Profile docs/config schemas, evidence generator inputs, reports, CLI/MCP, batch | Yes |
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

Current known gaps after benchmark Phase C:

- Real online provider smoke gates are optional and not part of default CI.
- A selected real VCEP profile pilot has not been implemented.
- Larger real-world hospital annotation validation has not been completed.
- CNV/SV interpretation is not supported.
