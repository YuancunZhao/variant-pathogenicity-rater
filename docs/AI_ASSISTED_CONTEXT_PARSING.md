# AI-Assisted Clinical Context Parsing

AI-assisted clinical-context parsing is an optional review aid for
natural-language variant input. It can suggest disease and phenotype context
when rule-based parsing is incomplete, but it is parser context only. It does
not generate ACMG evidence and does not change classification rules.

## Default Behavior

The default `rate_variant_from_text` path remains rule-based. It extracts only
explicit variant, transcript, genomic coordinate, disease, inheritance, and
report-option fields from the user text.

AI-assisted context parsing runs only when explicitly enabled:

```bash
vpr rate-text --text "BRCA1 NM_007294.4:c.68_69delAG, suspected HBOC phenotype" \
  --ai-assisted-context
```

Inside the package this is a provider boundary, not a live network dependency.
Tests use deterministic injected parsers. If no AI context parser provider is
available, the wrapper returns a visible limitation and no AI-derived context is
used for rating.

## Output Fields

Natural-language parse results may include:

- `ai_assisted_context`
- `context_candidates`
- `confirmed_context`
- `context_confirmation_required`
- `context_used_for_rating`

AI-derived context candidates include disease names, optional normalized disease
names or IDs, HPO terms, inheritance, confidence, source text spans, language,
ambiguity warnings, limitations, and provenance.

Every AI-derived disease or phenotype field is marked:

```json
{
  "parser_source": "ai_assisted",
  "requires_user_confirmation": true
}
```

## Confirmation Workflow

First run with AI-assisted context enabled to collect candidates:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nbreast and ovarian cancer history\nAD",
    "options": {
      "ai_assisted_context": true,
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

The candidate context is displayed for review. It is not copied into
`disease`, `inheritance`, or `gene_disease_context`.

After user or curator confirmation, rerun with `confirmed_context`:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nbreast and ovarian cancer history\nAD",
    "options": {
      "confirmed_context": {
        "disease_name": "hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant",
        "hpo_terms": [
          {"label": "Breast cancer", "hpo_id": "HP:0100013"}
        ]
      },
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

Confirmed context is mapped into the existing `rate_variant` context path and
still goes through the normal context-consistency and evidence safety checks.

## Safety Boundaries

- AI parsing is never evidence generation.
- Unconfirmed AI context is not mapped to `gene_disease_context`.
- Unconfirmed candidates cannot increase confidence for PVS1, PM2/population,
  PS1, PM5, or other context-sensitive criteria.
- Ambiguous disease candidates remain candidates and require confirmation.
- Disease mismatch remains a review flag or limitation.
- Missing confirmation keeps context-sensitive evidence conservative.
- The ACMG combiner and evidence generator decision trees are unchanged.
- AI-derived fields are visible in JSON output and wrapper-level markdown review
  sections.

## MCP Tools

`rate_variant_from_text` performs parse plus rating orchestration. `parse_variant_text`
is available for parser-only workflows and returns no `rate_variant_result`.

Both tools use a Codex-compatible top-level schema:

- top-level `type: object`
- top-level `additionalProperties: false`
- no top-level `oneOf`, `anyOf`, `enum`, or `not`
- required `text`

## CLI

`vpr rate-text` supports:

- `--ai-assisted-context`
- `--confirmed-context` with an inline JSON object or JSON file path
- `--no-require-context-confirmation`

Markdown output prepends a parsed-input review block and a clinical-context
review block before the rating report.
