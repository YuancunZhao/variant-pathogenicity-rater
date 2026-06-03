# Literature Suggested to Reviewed Evidence Workflow

This workflow converts ACMG Literature Evidence Agent suggestions into a
manual curation draft. It does not apply evidence and does not change the
classification combiner.

It is part of the current semi-automated interpretation loop:

```text
variant input
  -> normalization / annotation / context consistency
  -> automatic applied evidence generation
  -> candidate/suggested evidence
  -> manual reviewed evidence
  -> combiner
  -> report
```

Literature suggestions are review material. They can become combiner-counted
evidence only after a curator edits the draft into a valid `reviewed_applied`
record and supplies it through the manual reviewed evidence workflow.

## Flow

1. Life Science Research, Codex, local fixtures, or a curator gathers
   literature context.
2. `search_and_summarize_literature` can build search templates, normalize
   caller-supplied records, collapse duplicates, summarize criterion-specific
   claims, and emit `suggested_evidence` only. `assess_literature_evidence`
   remains the compatibility path for already structured literature records.
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
- General literature search output is also non-applied. Its
  `suggested_strength` values are reviewer guidance only.
- `source_candidate_evidence_id`, PMID, DOI, citation, extracted claim,
  review questions, and provenance are retained for traceability.
- Drafts include blank curator fields and are not ready for application.
- The classification combiner is unchanged; it sees only strict
  `reviewed_applied` records after curator confirmation.
- `reviewed_rejected` and `needs_more_info` records remain review notes and are
  not counted.
- The workflow does not silently convert literature candidates for `PS3`,
  `BS3`, `PS2`, `PM6`, `PP1`, `PS4`, `PP4`, `PM3`, `PS1`, or `PM5` into applied
  evidence.
- Provenance and audit trail fields are required to preserve article,
  extraction, draft, and curator-review traceability.

## CLI

```bash
vpr literature-search \
  --gene GENE1 \
  --variant NM_000001.1:c.76A\>G \
  --disease "GENE1 disorder" \
  --literature-records records.json

vpr literature-draft-reviewed \
  --literature-assessment-json examples/literature_agent_output.json \
  --output reviewed_draft.json
```

## MCP

Use `search_and_summarize_literature` for general search, deduplication,
criterion summaries, blocking flags, and reviewed draft output.

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
