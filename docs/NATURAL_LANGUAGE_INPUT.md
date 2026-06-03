# Natural Language Variant Input

The natural-language input wrapper lets users provide a short sentence or HGVS
text, then runs the existing `rate_variant` workflow with the parsed structured
fields.

This wrapper is not an evidence generator and is not an AI rater. By default it
uses local regex and finite dictionaries only. It does not call an LLM, does not
use the network, does not normalize aliases unless explicitly
dictionary-backed, and does not modify the ACMG combiner or evidence
generators.

Optional AI-assisted disease and phenotype parsing is available only as an
explicit opt-in parser-context aid. AI-derived disease/HPO context is always
marked `requires_user_confirmation=true`, remains visible for review, and is
not used as applied context unless a user or curator supplies
`confirmed_context`.

## CLI

```bash
vpr rate-text --text "BRCA1 NM_007294.4:c.68_69delAG, HBOC, AD"
vpr rate-text --text $'BRCA1 NM_007294.4:c.68_69delAG\nHereditary breast and ovarian cancer syndrome\nAD'
vpr rate-text --text "评估 BRCA1 185delAG，遗传性乳腺卵巢癌综合征，常染色体显性遗传"
vpr rate-text --text "GRCh38 chr17:43124027 CA>C BRCA1" --output markdown-zh
vpr rate-text --text "BRCA1 NM_007294.4:c.68_69delAG, breast and ovarian cancer phenotype" --ai-assisted-context
```

Supported output values are `json`, `markdown`, and `markdown-zh`. Markdown
output prepends parsed-input and clinical-context review blocks before the
generated report.

## Python API

```python
from variant_pathogenicity_rater.natural_language_input import (
    parse_variant_text,
    rate_variant_from_text,
)

parsed = parse_variant_text("CFTR NM_000492.4:c.1521_1523delCTT p.Phe508del, cystic fibrosis, AR")
result = rate_variant_from_text("GJB2 c.35delG hearing loss AR")
```

`parse_variant_text` returns `parsed_input`, `missing_fields`,
`ambiguity_warnings`, `normalization_warnings`, `alias_candidates`, and optional
clinical-context candidate fields.
`rate_variant_from_text` returns the same parser review fields plus the nested
existing `rate_variant_result`.

AI-assisted context parsing can be tested with an injected parser provider. The
package does not add a default live LLM or network dependency:

```python
def ai_context_provider(text, parsed):
    return {
        "disease_candidates": [
            {
                "disease_name": "hereditary breast and ovarian cancer syndrome",
                "confidence": 0.72,
                "evidence_text_span": "breast and ovarian cancer phenotype",
            }
        ]
    }

result = rate_variant_from_text(
    "BRCA1 NM_007294.4:c.68_69delAG, breast and ovarian cancer phenotype",
    options={"ai_assisted_context": True},
    ai_assisted_parser=ai_context_provider,
)
```

## MCP

The MCP tool is `rate_variant_from_text`.

```json
{
  "text": "BRCA1 NM_007294.4:c.68_69delAG, HBOC, AD",
  "output": "json",
  "language": "en",
  "options": {
    "include_population": false,
    "include_computational": false,
    "include_clinvar": false,
    "include_literature": false
  }
}
```

The MCP input schema is strict at the top level and requires `text`.

For parser-only workflows, MCP also exposes `parse_variant_text`. It accepts
the same input shape and returns parser review fields without running
`rate_variant`.

### Codex MCP Tool Selection

Codex should call `rate_variant_from_text` whenever the user provides
natural-language, multi-line, or HGVS+disease+inheritance mixed text.

Example user input:

```text
BRCA1 NM_007294.4:c.68_69delAG
Hereditary breast and ovarian cancer syndrome
AD
```

Bad call:

```json
{
  "name": "rate_variant",
  "arguments": {
    "value": "BRCA1 NM_007294.4:c.68_69delAG\nHereditary breast and ovarian cancer syndrome\nAD",
    "input_type": "hgvs"
  }
}
```

Correct call:

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
For natural-language, multi-line, or HGVS+disease+inheritance mixed text, call
rate_variant_from_text with the original text. Do not pass the whole text block
to rate_variant.value. Call rate_variant directly only when fields are already
structured as gene/transcript/hgvs_c/disease/inheritance.
```

`input_type=hgvs` is only for a pure HGVS variant string. It is not appropriate
for natural-language paragraphs or mixed text that includes disease,
inheritance, phenotype, or report-language instructions.

## Parsing Scope

The parser extracts only fields that are explicit in the input:

- `gene`
- `transcript`
- `hgvs_c`
- `hgvs_p`
- `chromosome`
- `position`
- `ref`
- `alt`
- `genome_build`
- `disease`
- `inheritance`
- report options

Inheritance aliases are limited to the built-in dictionary, for example `AD`
and `常染色体显性遗传` map to `autosomal_dominant`, while `AR` and
`常染色体隐性遗传` map to `autosomal_recessive`.

Disease aliases are also finite, for example `HBOC` and
`遗传性乳腺卵巢癌综合征` map to hereditary breast and ovarian cancer,
`CF` maps to cystic fibrosis, and `PKU` maps to phenylketonuria.

For common multi-line inputs, a line that is not a variant, gene, transcript,
coordinate, inheritance term, or report option may be extracted as `disease`
when it explicitly contains a disease keyword such as `disease`, `syndrome`,
`cancer`, `carcinoma`, `cardiomyopathy`, `hearing loss`, `fibrosis`,
`phenylketonuria`, `综合征`, `疾病`, `肿瘤`, `癌`, `耳聋`, `听力损失`,
`囊性纤维化`, `苯丙酮尿症`, or `心肌病`. If multiple disease-like lines are
present, the parser reports ambiguity and does not choose one automatically.

Short variant aliases such as `185delAG` are returned as `alias_candidates`.
They are not silently converted into HGVS or genomic coordinates.

## AI-Assisted Clinical Context

AI-assisted disease and phenotype parsing is off by default. Enable it with
`options.ai_assisted_context=true` or CLI `--ai-assisted-context`.

AI-assisted context runs only as a second stage after rule-based variant
parsing. It is intended for cases where the disease is missing, disease parsing
is ambiguous, or phenotype text appears complex. The output is placed in
`ai_assisted_context` and `parsed_input.context_candidates`.

Unconfirmed AI-derived context is not copied into top-level `disease`,
`inheritance`, or `gene_disease_context`, and it cannot increase confidence for
PVS1, PM2/population, PS1, PM5, or any context-sensitive criterion. To use a
candidate context, rerun with `options.confirmed_context` or
`options.reviewed_context`.

Example confirmation payload:

```json
{
  "text": "BRCA1 NM_007294.4:c.68_69delAG, breast and ovarian cancer phenotype",
  "options": {
    "confirmed_context": {
      "disease_name": "hereditary breast and ovarian cancer syndrome",
      "inheritance": "autosomal_dominant",
      "hpo_terms": [
        {"label": "Breast cancer", "hpo_id": "HP:0100013"}
      ]
    }
  }
}
```

See [AI_ASSISTED_CONTEXT_PARSING.md](AI_ASSISTED_CONTEXT_PARSING.md) for the
full confirmation workflow and safety boundary.

## Safety Boundaries

- Missing transcript is reported because PVS1/PS1/PM5 may be limited.
- Missing genomic coordinate is reported because PM2, population evidence, and
  parts of PVS1 may be limited.
- Missing disease or inheritance is reported because evidence confidence may be
  limited.
- Parser warnings are review context only and never become `EvidenceItem`
  records.
- AI-derived disease/HPO fields are parser candidates only until explicitly
  confirmed.
- The existing `rate_variant` workflow remains the only rating workflow.
- All outputs remain human-review-required.
