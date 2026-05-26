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

If the task touches release readiness, also read:

- `docs/RELEASE_READINESS.md`
- `docs/BENCHMARK.md`
- `docs/REAL_DATA_SMOKE.md`

If the task touches literature evidence, also read:

- `docs/ACMG_LITERATURE_AGENT.md`
- `docs/LITERATURE_AGENT_SAFETY.md`
- `skills/acmg-literature-evidence.md`

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
- Keep benchmark and smoke expectations conservative.

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
