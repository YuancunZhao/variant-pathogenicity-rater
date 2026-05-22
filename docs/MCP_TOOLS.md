# MCP Tools

## Overview

The MCP server exposes auditable tools for SNV/small indel ACMG rating. The
tools should use Pydantic v2 schemas internally and expose JSON schemas through
MCP.

Phase 1 tools:

- `health_check`
- `rate_variant`
- `normalize_variant`
- `query_clinvar`
- `query_population_frequency`
- `evaluate_population_rules`
- `evaluate_pvs1`
- `evaluate_computational_evidence`
- `search_literature_evidence`
- `generate_report`

All tools should return structured errors and should preserve audit metadata
when evidence is retrieved or interpreted.

## Shared Response Requirements

Every evidence-producing tool should include:

- Source name
- Source version or retrieval date
- Query parameters
- Retrieval timestamp
- Evidence ID
- Provenance block
- Limitations or warnings

Every interpretation-producing tool should include:

- Criterion or classification result
- Rationale
- Evidence references
- Confidence or uncertainty indicator
- Human review requirement where applicable

## Tool: health_check

Readiness probe for the MCP server process and dynamic tool registry.

Responsibilities:

- Confirm the MCP server is reachable over stdio JSON-RPC
- Confirm tool discovery and registration are available
- Return version and environment-level readiness information
- Avoid performing any evidence retrieval or ACMG interpretation

Input shape:

```json
{}
```

Output shape:

```json
{
  "status": "ok",
  "service": "variant-pathogenicity-rater",
  "stage": "mcp_framework",
  "checks": {
    "mcp_server": "ok",
    "tool_registry": "ok"
  }
}
```

## Tool: rate_variant

Primary end-to-end workflow tool.

Responsibilities:

- Accept HGVS or VCF-like input
- Normalize the variant
- Retrieve configured evidence
- Evaluate supported ACMG criteria
- Combine criteria into a five-tier machine proposal
- Generate evidence chain and report
- Mark human review as required

Input shape:

```json
{
  "variant": {
    "input_type": "hgvs",
    "value": "NM_000059.4:c.5946delT",
    "genome_build": "GRCh38"
  },
  "options": {
    "include_clinvar": true,
    "include_population": true,
    "include_computational": true,
    "include_literature": true
  }
}
```

Output shape:

```json
{
  "normalized_variant": {},
  "evidence_chain": {},
  "criteria": [],
  "classification_result": {
    "classification": "Likely pathogenic",
    "human_review_required": true
  },
  "report": {}
}
```

## Tool: normalize_variant

Responsibilities:

- Parse HGVS or VCF-like input
- Convert to NormalizedVariant
- Validate SNV/small indel scope
- Return normalization warnings

Input shape:

```json
{
  "input_type": "vcf_like",
  "chrom": "13",
  "pos": 32316461,
  "ref": "T",
  "alt": "",
  "genome_build": "GRCh38"
}
```

Output shape:

```json
{
  "status": "normalized",
  "input_format": "vcf_like",
  "normalized_variant": {
    "variant_id": "GRCh38-13-32316461-AT-A",
    "variant_type": "small_deletion",
    "genome_build": "GRCh38",
    "chrom": "13",
    "pos": 32316461,
    "ref": "AT",
    "alt": "A",
    "hgvs_g": null,
    "hgvs_c": null,
    "hgvs_p": null
  },
  "unresolved_fields": [],
  "human_review_required": true,
  "normalization_warnings": []
}
```

Unsupported inputs must return a structured error rather than partial
interpretation.

Phase 1 normalization does not perform liftover, transcript-to-genome mapping,
or external API standardization. HGVS strings and transcript accessions are
preserved, and locally unresolved fields are returned in `unresolved_fields`.

## Tool: query_clinvar

Responsibilities:

- Retrieve or adapt ClinVar assertion evidence
- Return standard EvidenceItem objects
- Preserve ClinVar accession, review status, clinical significance, submitter
  summary, and retrieval metadata

Input shape:

```json
{
  "normalized_variant": {},
  "include_submitter_details": false
}
```

Output shape:

```json
{
  "evidence_items": [
    {
      "evidence_id": "ev_clinvar_001",
      "evidence_type": "clinical_assertion",
      "source": {
        "name": "ClinVar",
        "version": "retrieved_2026-05-21",
        "url": "https://www.ncbi.nlm.nih.gov/clinvar/"
      },
      "data": {},
      "provenance": {}
    }
  ]
}
```

ClinVar evidence should inform the evidence chain but should not bypass ACMG
criterion evaluation or human review.

## Tool: query_population_frequency

Responsibilities:

- Retrieve population frequency evidence
- Return allele counts, allele numbers, allele frequency, and population-specific
  observations when available
- Provide evidence for BA1, BS1, and PM2 evaluators

Input shape:

```json
{
  "normalized_variant": {},
  "sources": ["gnomAD"]
}
```

Output shape:

```json
{
  "evidence_items": [
    {
      "evidence_id": "ev_pop_001",
      "evidence_type": "population_frequency",
      "data": {
        "allele_frequency": 0.000001,
        "allele_count": 1,
        "allele_number": 1500000
      },
      "supports_criteria": ["PM2"],
      "opposes_criteria": ["BA1", "BS1"],
      "provenance": {}
    }
  ]
}
```

## Tool: evaluate_population_rules

Responsibilities:

- Evaluate BA1, BS1, and PM2 from a supplied `PopulationFrequency`
- Apply disease/context safety gates before criteria can be treated as applied
- Keep no-record, low-quality, ancestry-mismatch, and incomplete-context results
  as limitations or candidate-only evidence

Input shape:

```json
{
  "variant": {},
  "gene_disease_context": {},
  "population_frequency": {},
  "thresholds": {}
}
```

Output shape:

```json
{
  "evidence_items": [
    {
      "code": "PM2",
      "strength": "supporting",
      "direction": "pathogenic",
      "requires_review": true
    }
  ],
  "human_review": {
    "required": true
  }
}
```

## Tool: evaluate_pvs1

Responsibilities:

- Evaluate PVS1 for SNV/small indel loss-of-function variants
- Support nonsense, frameshift, canonical ±1/2 splice-site, start-loss, and
  small indel LoF consequences
- Consider LoF disease mechanism, transcript relevance, NMD prediction,
  last-exon or terminal-region context, and possible in-frame rescue
- Return PVS1 level, reasoning chain, downgrade rationale, confidence,
  review flags, EvidenceItem records, and a CriterionAssessment-style block

Input shape:

```json
{
  "variant": {},
  "transcript": {},
  "gene_disease_context": {
    "gene": "BRCA2",
    "disease": "Hereditary breast and ovarian cancer syndrome",
    "inheritance": "autosomal dominant",
    "lof_is_known_mechanism": true,
    "transcript_is_biologically_relevant": true,
    "nmd_prediction_available": true,
    "nmd_predicted": true,
    "last_exon_information": {
      "is_in_last_exon": false,
      "within_terminal_region": false,
      "distance_to_last_exon_junction": 1200
    }
  }
}
```

Output shape:

```json
{
  "pvs1": {
    "outcome": "PVS1",
    "reasoning_chain": [
      "Predicted LoF consequence detected: frameshift.",
      "LoF is provided as a known disease mechanism.",
      "Transcript is provided as biologically or clinically relevant.",
      "Variant is predicted to result in NMD."
    ],
    "downgrade_rationale": [],
    "confidence": 0.86,
    "requires_review": true,
    "predicted_consequence": "frameshift",
    "nmd_predicted": true
  },
  "evidence_items": [],
  "criterion_assessment": {
    "criterion": "PVS1",
    "status": "met",
    "strength": "very_strong",
    "applied_pvs1_level": "PVS1",
    "rationale": "Predicted loss-of-function variant in a gene where loss of function is an established disease mechanism.",
    "evidence_refs": ["ev_consequence_001", "ev_gene_mechanism_001"],
    "requires_human_review": true
  },
  "review_flags": []
}
```

Phase 1 PVS1 must not evaluate exon-level deletions, CNVs, SV breakpoints, or
long-read evidence.

## Tool: evaluate_computational_evidence

Responsibilities:

- Evaluate PP3 and BP4 from computational prediction evidence
- Return criterion assessments for supported computational evidence
- Surface conflicts or insufficient evidence

Input shape:

```json
{
  "normalized_variant": {},
  "evidence_items": []
}
```

Output shape:

```json
{
  "criterion_assessments": [
    {
      "criterion": "PP3",
      "status": "met",
      "strength": "supporting",
      "rationale": "Multiple computational methods support a deleterious effect.",
      "evidence_refs": ["ev_comp_001"],
      "requires_human_review": true
    }
  ]
}
```

## Tool: search_literature_evidence

Responsibilities:

- Search or adapt candidate literature evidence
- Return citation-level EvidenceItem objects
- Identify possible relevance to variant, gene, disease, function, segregation,
  or case observations
- Avoid automatically assigning complex ACMG evidence in phase 1 unless a future
  evaluator explicitly supports it

Input shape:

```json
{
  "normalized_variant": {},
  "query_terms": ["BRCA2", "c.5946delT"],
  "max_results": 20
}
```

Output shape:

```json
{
  "evidence_items": [
    {
      "evidence_id": "ev_lit_001",
      "evidence_type": "literature",
      "source": {
        "name": "PubMed",
        "version": "retrieved_2026-05-21"
      },
      "data": {
        "pmid": "00000000",
        "title": "Example title",
        "candidate_relevance": ["variant", "gene"]
      },
      "provenance": {}
    }
  ]
}
```

## Tool: generate_report

Responsibilities:

- Render the structured evidence chain and classification result
- Produce JSON and Markdown report forms
- Include human review requirement
- Include audit summary

Input shape:

```json
{
  "normalized_variant": {},
  "evidence_items": [],
  "criterion_assessments": [],
  "classification_result": {}
}
```

Output shape:

```json
{
  "report": {
    "format": "json",
    "normalized_variant": {},
    "evidence_chain": {},
    "classification_result": {},
    "human_review": {
      "required": true,
      "status": "pending"
    }
  },
  "markdown": "# Variant Pathogenicity Report\n"
}
```

## Tool Error Handling

All tools should use structured errors.

Recommended error fields:

- `code`
- `message`
- `details`
- `recoverable`

Examples:

- `UNSUPPORTED_VARIANT_TYPE`
- `INVALID_HGVS`
- `INVALID_VCF_LIKE_INPUT`
- `EVIDENCE_SOURCE_UNAVAILABLE`
- `INSUFFICIENT_EVIDENCE`
- `SCHEMA_VALIDATION_ERROR`

## Audit Requirements

Every output from `rate_variant` must support these traceability questions:

- What input was rated?
- How was it normalized?
- Which evidence sources were queried?
- What query was sent to each source?
- When was each source queried?
- Which evidence items support each criterion?
- Which criteria support the final machine proposal?
- Where is human review required?
