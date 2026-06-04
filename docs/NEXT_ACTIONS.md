# Next Actions

This file lists the highest-value next tasks for the current project state.
Before starting any task, read `docs/PROJECT_STATE.md`,
`docs/ROADMAP_CURRENT.md`, `docs/KNOWN_LIMITATIONS.md`, and
`docs/APPLIED_EVIDENCE_GENERATION.md`. For the current applied evidence status
review, also read `docs/APPLIED_EVIDENCE_STATUS.md`.

## Recommended Next Task

The recommended next task is `63_selected_real_world_case_validation`.

It is the best next step because the 74 real provider pipeline is implemented,
the 75 live-provider smoke validation layer is available behind explicit
environment gates, the 76 mock/fixture interface audit activation makes
provider outcomes and unresolved placeholders visible, and the 77A output
schema unification gives Python, CLI, MCP, batch, and annotated-batch clients a
canonical additive output view while preserving legacy fields. The 77B provider
interface consolidation now backs provider summaries with a normalized runtime
contract while preserving raw provider step payloads, and the 77C evidence
status helper unification centralizes read-only applied/candidate/review-note
status grouping without changing evidence logic. The 77D-1 RuntimeOptions
foundation now centralizes the Python API `rate_variant` core option path while
leaving CLI/MCP/batch/text wrapper migration to later 77D work. Default
workflows remain no-network, and online ClinVar, gnomAD, Ensembl VEP, PubMed,
and LitVar surfaces are opt-in only.
Selected real-world case validation should now exercise transcript resolution,
provider gaps, ClinVar comparator ambiguity, ERepo review notes, literature
summary/draft behavior, duplicate literature/case handling, and report wording
without changing evidence logic or the combiner.

## Prioritized Task List

| Task name | Priority | Short summary | Risk level | Expected modules touched | Combiner must remain untouched |
| --- | --- | --- | --- | --- | --- |
| `77C_evidence_status_helper_unification` | Done | Added a shared read-only evidence status helper and canonical status summary fields while preserving applied/candidate boundaries, reviewed-evidence validation, and classification. | Medium-high | Evidence status helper, pipeline grouping reads, canonical evidence summary, reports, docs, tests | Yes |
| `77D-1_runtime_options_foundation` | Done | Added a centralized RuntimeOptions foundation for the Python API `rate_variant` core option path while preserving legacy options, provider mapping semantics, default offline/mock behavior, and reviewed-evidence boundaries. | Medium | Runtime options helper, rate_variant option adapter, focused tests, docs | Yes |
| `77B_provider_interface_consolidation` | Done | Added a normalized provider runtime result contract and adapter-backed provider summaries without changing provider internals, evidence generation, or classification. | Medium | Provider runtime contract, pipeline summary adapter, canonical provider output, CLI/MCP output tests, docs | Yes |
| `77A_output_schema_unification` | Done | Added additive canonical output sections for single, text, batch, annotated-batch, CLI JSON, and MCP outputs while preserving legacy fields and leaving combiner/evidence logic unchanged. | Medium | Pipeline output view, batch summaries, CLI/MCP output tests, docs | Yes |
| `76_mock_fixture_interface_audit_and_activation` | Done | Added explicit provider outcome summaries, clarified `mock_mode`/`data_source_modes` semantics, preserved structured coordinates in variant resolution, bridged VEP descriptive protein/consequence facts into resolution only, and kept provider facts behind existing evaluator/review boundaries. | High | Pipeline outputs, provider provenance summaries, variant resolution, online-provider tests, docs | Yes |
| `75_live_provider_smoke_validation` | Done | Added explicitly env-gated live smoke validation for completed online providers, checking reachability, cache/provenance, parser resilience, failure-to-limitation behavior, CLI smoke, and MCP online-option schema compatibility without default network dependency. | High | Smoke docs, optional smoke fixtures, provider cache/provenance review | Yes |
| `63_selected_real_world_case_validation` | P0 | Validate selected real-world SNV/small-indel cases with completed provider boundaries, provenance review, and no direct provider classification. | High | Case fixtures, validation docs, report examples | Yes |
| `74_real_provider_pipeline` | Done | Added opt-in online ClinVar, gnomAD, Ensembl VEP, PubMed, and LitVar provider adapters with shared HTTP/cache/provenance handling, CLI/MCP online options, default-off safety, and mocked offline validation. Integration review passed with `655 passed, 2 skipped`. | High | Online providers, CLI/MCP, provenance/cache docs, tests | Yes |
| `72_online_pubmed_litvar_adapter_pilot` | Done | Implemented opt-in PubMed/LitVar adapters for the completed literature engine while keeping offline/local fixtures as default validation. | High | Literature providers, provenance/cache docs, optional smoke tests | Yes |
| `61_selected_real_vcep_profile_pilot` | P1 | Pilot one selected real VCEP profile only after toy profile, real provider validation, and benchmark Phase C pass. | High | Profile config, provenance docs, reports, benchmark cases | Yes |
| `76_provider_cache_reproducibility_hardening` | P1 | Harden provider cache reproducibility expectations after live smoke review: cache key review, raw-hash audit, source-version freshness checks, and replay documentation. | Medium | Provider cache docs, provenance audit docs, optional fixtures | Yes |
| `64_optional_online_smoke_gates` | Superseded by `75_live_provider_smoke_validation` | Standardize explicitly gated online smoke checks for provider reachability, cache/provenance, parser resilience, and failure-to-limitation behavior. | Medium | Provider smoke tests, docs, optional CI docs | Yes |
| `73_cnv_sv_framework_planning` | P2 | Plan future CNV/SV support as a design-only framework with separate variant models, validation, and safety boundaries. | High | Design docs, schema sketches, validation plan | Yes |
| `71_general_literature_search_and_summary_engine` | Done | Implemented and integration-reviewed general literature query planning, local/offline records, duplicate collapse, criterion summaries, blocking/review flags, CLI/MCP, report section, and reviewed drafts. | High | Literature agent, CLI/MCP, reports, docs, tests | Yes |
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
| `59_provider_provenance_audit` | Superseded by `76_mock_fixture_interface_audit_and_activation` | Provider source version, query, raw hash, cache hit, limitations, and requested/configured/outcome mode labels are now surfaced through `provider_mode_summary`. | Medium | Provider adapters, schemas, reports, docs, tests | Yes |
| `60_batch_report_consistency_audit` | P3 | Verify single, batch, annotated-batch, CLI, and MCP outputs preserve the same evidence separation and safety language. | Medium | Batch orchestration, reports, CLI/MCP output tests, docs | Yes |

## Guardrails For Selecting Work

Prefer tasks that strengthen safety, reviewability, provenance, and validation.
Avoid tasks that broaden variant scope or automate strong evidence without the
required clinical context.

Do not start CNV/SV, repeat, mitochondrial, methylation, trio/family-aware,
wet-lab/RNA, or clinical sign-out tasks as implementation work in the current
stage. Those belong in design or future validated tracks.

Current known gaps after 77D-1 RuntimeOptions foundation:

- CLI, MCP, batch, annotated-batch, and natural-language wrapper option
  normalization still use their existing wrapper-specific assembly paths and
  should be migrated in later 77D tasks without deleting public fields.
- Live provider smoke validation is implemented and remains outside default
  pytest/CI; current live endpoint results still depend on explicit local
  execution under `VPR_RUN_LIVE_PROVIDER_SMOKE=1`.
- Real-world case validation has not yet exercised the full completed
  literature-engine plus provider stack on selected cases.
- PubMed/LitVar online adapters are implemented but remain opt-in and
  candidate-only.
- A selected real VCEP profile pilot has not been implemented.
- Provider cache/reproducibility hardening remains a follow-up now that
  provider runtime outcomes and raw-hash/cache-hit fields are visible.
- Raw `step_results` are still a legacy compatibility/debug payload; migration
  into a canonical step-state model remains future work.
- Larger real-world hospital annotation validation has not been completed.
- CNV/SV interpretation is not supported; only framework planning is currently
  appropriate.
