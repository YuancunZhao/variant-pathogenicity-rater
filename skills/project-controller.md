# Project Controller Skill

Use this skill before starting any non-trivial task in Variant Pathogenicity
Rater. Its purpose is to keep Codex aligned with the current project state,
architecture boundaries, release gates, roadmap, and safety posture.

## Required Pre-Task Reading

Before planning or editing, read these files:

- `docs/PROJECT_STATE.md`
- `docs/ROADMAP_CURRENT.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/APPLIED_EVIDENCE_GENERATION.md`
- `docs/APPLIED_EVIDENCE_STATUS.md`

If the task touches release readiness, also read:

- `docs/RELEASE_READINESS.md`
- `docs/BENCHMARK.md`
- `docs/REAL_DATA_SMOKE.md`

If the task touches literature evidence, also read:

- `docs/ACMG_LITERATURE_AGENT.md`
- `docs/GENERAL_LITERATURE_ENGINE.md`
- `docs/LITERATURE_AGENT_SAFETY.md`
- `skills/acmg-literature-evidence.md`

If the task touches ClinGen Evidence Repository, ClinVar, external curated
sources, or reviewed-evidence drafts, also read:

- `docs/CLINGEN_EREPO_INTEGRATION.md`
- `docs/MANUAL_REVIEWED_EVIDENCE.md`
- `docs/APPLIED_EVIDENCE_STATUS.md`
- `docs/REAL_PROVIDER_VALIDATION_PLAN.md`
- `docs/REAL_PROVIDER_PIPELINE.md`
- `docs/ONLINE_PROVIDER_SAFETY.md`

If the task touches VCEP profiles, rule knowledge, profile overrides, or
disease/gene-specific guidance, also read:

- `docs/VCEP_SIGNAL_OVERRIDE_FRAMEWORK.md`
- `docs/RULE_KNOWLEDGE_BASE.md`

## Default Architecture Rules

1. Default to not changing the classification combiner.
2. Default to not relaxing safety rules.
3. Candidate evidence must not enter applied evidence automatically.
4. All applied evidence must have focused tests.
5. All providers must preserve provenance.
6. All online features must default to off and require explicit opt-in.
7. All provider failures, parser uncertainty, context conflicts, and unsupported
   inputs must become structured limitations, warnings, or failed records.
8. New evidence must be review-required.
9. New evidence must be report-separated as applied versus candidate/review-note.
10. New evidence must remain batch-compatible.
11. New evidence must remain CLI-compatible.
12. New evidence must remain MCP-compatible.
13. ClinVar, ClinGen ERepo, and literature outputs must not automatically
    classify variants.
14. Reviewed-evidence drafts must remain drafts until a curator explicitly
    submits valid `reviewed_applied` evidence.
15. VCEP signals alone must not change classification.
16. Approved VCEP profile overrides must not bypass generator safety gates.
17. Disabled VCEP-profile criteria must become candidate/review-note evidence,
    not silent deletions.
18. VCEP override provenance and report visibility are required.
19. Real provider validation must preserve local fixture/local snapshot
    coverage as the primary validation path.
20. Optional online providers must remain disabled by default and explicitly
    gated.
21. Provider cache, provenance, source version, query metadata, parser version,
    and limitations must stay visible.
22. Provider failures, misses, malformed payloads, stale sources, and context
    mismatches must degrade to limitations, review flags, failed records, or
    candidate-only output.
23. No provider directly changes classification.
24. Benchmark Phase C plus General Literature Engine and 74 Real Provider
    Pipeline integration review is the current regression baseline: 100
    offline curated SNV/small-indel cases, version
    `offline-curated-v4-phase-c`, fixture-backed providers including
    annotation/transcript metadata, opt-in online provider surfaces mocked in
    default tests, and latest full regression status `655 passed, 2 skipped`.
25. `search_and_summarize_literature` is implemented as a candidate-only
    literature workflow with query planning, local/offline records, duplicate
    collapse, criterion summaries, blocking/review flags, CLI/MCP/report
    surfaces, and reviewed drafts.
26. ClinVar online must not trigger PP5/BP6, PubMed/LitVar online must not
    create applied evidence, gnomAD/VEP online facts must flow only through
    existing population/computational evaluators, and a no-record gnomAD result
    must not trigger PM2.

## Evidence Governance

Applied evidence is evidence that can be passed to the ACMG classification
combiner. Candidate/review-note evidence is review support only. The distinction
is a safety boundary, not an implementation detail.

When adding or modifying evidence behavior:

- Preserve `requires_review` or equivalent human-review-required behavior.
- Preserve provenance for source, query, snapshot/version, run context, and
  limitations.
- Preserve context consistency checks for gene, transcript, disease,
  inheritance, ancestry, consequence, provider-record, and genome build.
- Preserve failure-to-limitation behavior.
- Keep report wording clear that machine output is a proposal.
- Keep benchmark and smoke expectations conservative. Benchmark expectations
  are safety regression expectations, not clinical truth labels.
- Keep ERepo exact matches, gene-level VCEP signals, literature suggestions,
  general literature summaries, and unsupported criterion suggestions outside
  the combiner unless explicitly converted through reviewed evidence.
- Keep VCEP profile overrides limited to approved, explicitly enabled,
  non-conflicting profiles and the documented safe override surface.
- Preserve `vcep_profile_summary` in batch and annotated-batch records when
  VCEP profile context is present.
- Keep current provider dependencies explicit: PVS1 depends on
  transcript/NMD/context/LoF mechanism, BA1/BS1/PM2 depends on population
  provider facts and thresholds, PP3/BP4 depends on computational provider
  consensus, and PS1/PM5 depends on ClinVar comparator plus protein/transcript
  matching.

## Planning Expectations

Before implementation, identify:

- Whether the task is roadmap-aligned.
- Whether it touches applied evidence, candidate evidence, provider behavior,
  reporting, CLI, MCP, batch, or release gates.
- Whether the combiner should remain untouched. The default answer is yes.
- Which tests or checks are needed for the risk level.
- Which documentation must be updated.

Do not implement a new ACMG evidence criterion or broaden variant scope unless
the task explicitly asks for it and the roadmap supports it.

The current recommended next task is env-gated live provider smoke validation,
followed by selected real-world case validation. Real provider validation is
complete for the current ClinVar, gnomAD, Ensembl VEP, PubMed/LitVar, MANE,
and ClinGen ERepo surfaces and should now be treated as a regression boundary.
Benchmark Phase C, Chinese report output, offline variant resolution, the
General Literature Search and Summary Engine, and the 74 Real Provider
Pipeline are complete and should be treated as the current safety regression
baseline.

Current next priorities are live provider smoke validation, selected
real-world case validation, a selected real VCEP profile pilot, provider
cache/reproducibility hardening, and CNV/SV framework planning. Current known
gaps include larger real-world hospital annotation validation and unsupported
CNV/SV interpretation.

## Completion Report

Every completed task must report:

- Modified files.
- Architecture impact.
- Safety impact.
- Tests run.
- Remaining risks.
- Recommended next task.

If no tests were run, say why. If the combiner was touched, explicitly explain
why, summarize the diff, and identify candidate-leakage tests. In normal
roadmap work, the combiner should remain unchanged.
