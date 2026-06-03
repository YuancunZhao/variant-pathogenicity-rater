# Natural-Language Variant Rating

Use this skill when a user wants Variant Pathogenicity Rater to accept a short
natural-language or HGVS-like sentence and rate it through the existing
`rate_variant` workflow.

## Tool Selection Rule

When the user input is natural language, multi-line text, or a mixed
HGVS/disease/inheritance paragraph, call MCP `rate_variant_from_text` first.
Do not pass the whole text block to `rate_variant.value`.

Use `rate_variant_from_text` for inputs like:

```text
BRCA1 NM_007294.4:c.68_69delAG
Hereditary breast and ovarian cancer syndrome
AD
```

The parser can extract an explicit disease/condition line in common multi-line
input when the line contains disease keywords such as `disease`, `syndrome`,
`cancer`, `cardiomyopathy`, `hearing loss`, `fibrosis`, `phenylketonuria`,
`综合征`, `疾病`, `癌`, `耳聋`, `听力损失`, `囊性纤维化`, `苯丙酮尿症`, or
`心肌病`. Multiple disease-like lines remain ambiguous and must not be chosen
automatically.

Use direct `rate_variant` only when the input is already structured into fields
such as `gene`, `transcript`, `hgvs_c`, `disease`, and `inheritance`.

`input_type=hgvs` is only for a pure HGVS variant string. It is not appropriate
for natural-language paragraphs or text blocks that include disease names,
inheritance terms, phenotype text, or report instructions.

Bad MCP call:

```json
{
  "name": "rate_variant",
  "arguments": {
    "value": "BRCA1 NM_007294.4:c.68_69delAG\nHereditary breast and ovarian cancer syndrome\nAD",
    "input_type": "hgvs"
  }
}
```

Correct MCP call:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nHereditary breast and ovarian cancer syndrome\nAD",
    "options": {
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

Codex instruction snippet:

```text
If the user provides natural-language, multi-line, or HGVS+disease+inheritance
mixed text, call rate_variant_from_text with the original text. Do not call
rate_variant with value=<entire text block>. Only call rate_variant directly
when the variant input is already split into structured fields.
```

## AI-Assisted Context Workflow

Default behavior is rule-based parsing. Use AI-assisted disease/phenotype
parsing only when the user explicitly opts in or asks Codex to help parse
unclear clinical context.

When AI-assisted context is enabled:

- First call `parse_variant_text` or `rate_variant_from_text` with
  `options.ai_assisted_context=true`.
- Treat returned `ai_assisted_context` and `context_candidates` as review-only
  candidates.
- Show the disease/HPO candidates and their text spans to the user.
- Do not pass unconfirmed AI candidates as `disease`, `inheritance`, or
  `gene_disease_context`.
- Rerun only after confirmation with `options.confirmed_context`.

AI-assisted candidate call:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nbreast and ovarian cancer phenotype\nAD",
    "options": {
      "ai_assisted_context": true,
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

Confirmed-context rerun:

```json
{
  "name": "rate_variant_from_text",
  "arguments": {
    "text": "BRCA1 NM_007294.4:c.68_69delAG\nbreast and ovarian cancer phenotype\nAD",
    "options": {
      "confirmed_context": {
        "disease_name": "hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant"
      },
      "report_language": "zh",
      "report_mode": "laboratory"
    }
  }
}
```

Unconfirmed AI disease/HPO context must not be used to raise confidence for
PVS1, PM2/population, PS1, PM5, or any other context-sensitive evidence.

## Safety Boundary

- The natural-language layer is parser-only.
- Do not use an LLM or network lookup to infer missing variant fields.
- AI-assisted disease/HPO parsing is opt-in, candidate-only, and always
  requires user confirmation.
- Do not silently normalize short aliases such as `185delAG`.
- Do not generate `EvidenceItem` records in the parser.
- Do not modify the ACMG combiner.
- Do not relax existing normalization, provider, or evidence safety rules.
- Always show `parsed_input`, missing fields, warnings, and alias candidates for
  human review.

## Supported Surfaces

- Python API:
  - `variant_pathogenicity_rater.natural_language_input.parse_variant_text`
  - `variant_pathogenicity_rater.natural_language_input.rate_variant_from_text`
- CLI:
  - `vpr rate-text --text "..."`
- MCP:
  - `parse_variant_text`
  - `rate_variant_from_text`

## Expected Output

Return parser review fields next to the normal rating result:

- `parsed_input`
- `missing_fields`
- `ambiguity_warnings`
- `normalization_warnings`
- `alias_candidates`
- `ai_assisted_context`
- `context_candidates`
- `confirmed_context`
- `context_confirmation_required`
- nested `rate_variant_result`
- `report`
- mandatory human-review notice

If no supported HGVS-like or genomic-coordinate variant shape is parsed, return
a structured error and do not call `rate_variant`.
