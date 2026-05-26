# Literature Suggested to Reviewed Evidence Workflow

This workflow converts ACMG Literature Evidence Agent suggestions into a
manual curation draft. It does not apply evidence and does not change the
classification combiner.

## Flow

1. Life Science Research gathers literature context.
2. `assess_literature_evidence` evaluates caller-supplied literature records
   and emits `suggested_evidence` only.
3. `create_reviewed_evidence_draft` or `vpr literature-draft-reviewed` converts
   the assessment JSON into `reviewed_evidence` draft templates.
4. A curator edits each draft, answers the `review_questions`, confirms the
   article and variant context, removes template-only metadata as needed, and
   supplies curator name, review date, rationale, and override reason.
5. Only after the curator explicitly sets `evidence_status` to
   `reviewed_applied` can the record be supplied to
   `rate_variant --reviewed-evidence`.

## Safety Behavior

- Literature suggestions are never automatically applied.
- Drafts default to `evidence_status: needs_more_info`,
  `curator_decision: pending`, and `requires_manual_review: true`.
- `source_candidate_evidence_id`, PMID, DOI, citation, extracted claim,
  review questions, and provenance are retained for traceability.
- Drafts include blank curator fields and are not ready for application.
- The classification combiner is unchanged; it sees only strict
  `reviewed_applied` records after curator confirmation.
- `reviewed_rejected` and `needs_more_info` records remain review notes and are
  not counted.

## CLI

```bash
vpr literature-draft-reviewed \
  --literature-assessment-json examples/literature_agent_output.json \
  --output reviewed_draft.json
```

## MCP

Use `create_reviewed_evidence_draft` with the full JSON output from
`assess_literature_evidence`:

```json
{
  "literature_assessment_json": {
    "literature_evidence_assessments": [],
    "suggested_evidence": [],
    "review_questions": []
  }
}
```

## Curator Application Gate

The draft is a template. Before it can be used with `rate_variant`, the curator
must explicitly change:

- `evidence_status` to `reviewed_applied`
- `curator_decision` from `pending` to a concrete decision
- `curator_name` and `review_date`
- `rationale` and `override_reason` as appropriate

The curated record should conform to the strict reviewed evidence schema
documented in [MANUAL_REVIEWED_EVIDENCE.md](MANUAL_REVIEWED_EVIDENCE.md).
