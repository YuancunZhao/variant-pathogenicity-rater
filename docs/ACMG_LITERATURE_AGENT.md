# ACMG Literature Evidence Agent

The ACMG Literature Evidence Agent is an optional, non-invasive add-on for literature-derived ACMG evidence suggestions. It is not part of the default `rate_variant` pipeline and does not modify the ACMG classification combiner.

## Positioning

The agent produces `suggested_evidence`, not `applied_evidence`. Its output is intended to help a qualified reviewer decide whether literature evidence may support ACMG criteria after manual appraisal.

It never:

- applies ACMG evidence automatically
- changes final classification
- relaxes literature safety rules
- treats AI extraction as clinical sign-out
- changes population, PVS1, computational, transcript, or context-consistency behavior

## Supported Evidence Types

- PS3 / BS3: functional evidence
- PS2 / PM6: de novo evidence
- PP1: segregation evidence
- PS4: case enrichment or case-count evidence
- PP4: phenotype specificity
- PM3: trans observation
- PS1 / PM5: same amino acid or same residue evidence

## Offline / Online Behavior

The MCP tool `assess_literature_evidence` is offline by default. It accepts caller-provided structured `literature_records`, optional `pmids`, and optional `search_query`.

`use_online_search` defaults to `false`. If set to `true`, the agent records that online search was requested, but online retrieval failures must degrade safely and must not crash the tool or create applied evidence.

## Manual Review Requirements

Every assessment has `requires_manual_review=true` and includes `reason_not_applied`.

Key gates:

- PS3/BS3 require explicit assay validity, adequate controls, and clear functional direction before supporting-level suggestion.
- PS2 requires confirmed de novo status and confirmed parentage; otherwise use PM6 or candidate-only.
- PP1 requires segregation count and pedigree context.
- PS4 cannot be strong from a single case report; it requires multiple unrelated cases or enrichment/case-control logic.
- PP4 is candidate/review-only and cannot independently drive classification.
- PM3 requires explicit trans phase.
- PS1/PM5 must distinguish same amino acid, same residue different missense, same codon, and nearby residue.

## Recommended Workflow

1. Run the default `rate_variant` workflow if a baseline machine proposal is needed.
2. Separately call `assess_literature_evidence` with curated literature records.
3. Review suggested evidence, extracted claims, citations, limitations, and review questions.
4. If a human reviewer accepts any criterion, apply it outside this agent using the project’s existing reviewed-evidence workflow.

## Report Section

The optional report helper `render_literature_evidence_section` renders a separate section titled `Literature Evidence Assessment`.

The section explicitly states:

> Not automatically applied to ACMG classification

It is separate from `Applied ACMG Evidence` and does not alter final classification wording.

## Limitations

- Structured records are preferred; free-text extraction is intentionally conservative.
- PMIDs alone are not retrieved in offline mode.
- Duplicate cohorts, families, and overlapping cases require manual review.
- Functional assay validity and disease-mechanism fit require domain expertise.
- This agent is decision support only.
