# Life Science Research Workflow for ACMG Literature Evidence

This workflow describes how to pair Codex / Life Science Research-style literature retrieval with this project's `assess_literature_evidence` MCP tool.

The boundary is intentional:

- Life Science Research is responsible for searching, reading, and extracting literature facts.
- Variant Pathogenicity Rater is responsible for structuring those facts as ACMG literature evidence suggestions.
- The literature agent produces `suggested_evidence` only.
- `suggested_evidence` is not `applied_evidence` and does not change classification.
- Human review is required before any literature-derived ACMG criterion is applied elsewhere.

This repository remains offline by default. The Life Science Research step may be performed outside this project or with a separate configured workflow, then passed into this project as structured `literature_records`.

## Recommended Workflow

1. Use Life Science Research to search for the gene, variant, and disease.
2. Read abstracts, available full text, case tables, supplemental tables, and assay sections.
3. Extract PMID, DOI, title, year, journal, key sentence or claim, and evidence type.
4. Structure the findings as `literature_records`.
5. Pass those records to the `assess_literature_evidence` MCP tool.
6. Review the returned `literature_evidence_assessments`, `suggested_evidence`, `review_questions`, citations, and limitations.
7. Decide manually whether any item should be converted into reviewed applied evidence outside this literature agent.

The tool call should look conceptually like this:

```json
{
  "gene": "GENE1",
  "variant": "NM_000001.1:c.76A>G",
  "transcript": "NM_000001.1",
  "disease": "GENE1-related example disorder",
  "inheritance": "autosomal dominant",
  "phenotype": ["HP:0001250", "HP:0001263"],
  "literature_records": [
    {
      "pmid": "11111111",
      "doi": "10.0000/example.1",
      "title": "Functional assessment of GENE1 c.76A>G in a disease model",
      "year": 2024,
      "journal": "Example Genetics",
      "gene": "GENE1",
      "variant": "NM_000001.1:c.76A>G",
      "disease": "GENE1-related example disorder",
      "extracted_claim": "The variant showed reduced activity in a validated assay with adequate controls.",
      "claim": "The variant showed reduced activity in a validated assay with adequate controls.",
      "evidence_type": "functional",
      "assay_validity": "validated",
      "controls_adequate": true,
      "functional_direction": "reduced_function",
      "phenotype_match": "specific"
    }
  ],
  "use_online_search": false
}
```

## Query Templates

Use exact HGVS forms where possible, and repeat searches with common aliases, protein notation, rsID, and disease synonyms.

Functional evidence:

```text
"{GENE}" "{VARIANT}" functional assay "{DISEASE}"
"{GENE}" "{PROTEIN_VARIANT}" activity assay loss of function
"{GENE}" "{VARIANT}" in vitro functional characterization
"{GENE}" "{VARIANT}" validated assay controls
```

De novo:

```text
"{GENE}" "{VARIANT}" de novo "{DISEASE}"
"{GENE}" "{PROTEIN_VARIANT}" proband parents confirmed
"{GENE}" "{VARIANT}" trio sequencing
"{GENE}" "{VARIANT}" paternity maternity confirmed
```

Segregation:

```text
"{GENE}" "{VARIANT}" segregation family "{DISEASE}"
"{GENE}" "{PROTEIN_VARIANT}" pedigree affected unaffected
"{GENE}" "{VARIANT}" cosegregation
"{GENE}" "{VARIANT}" informative meioses
```

Case report / PS4:

```text
"{GENE}" "{VARIANT}" case report "{DISEASE}"
"{GENE}" "{VARIANT}" case series unrelated
"{GENE}" "{VARIANT}" affected individuals controls
"{GENE}" "{VARIANT}" enrichment cases controls
```

Trans observation / PM3:

```text
"{GENE}" "{VARIANT}" compound heterozygous trans
"{GENE}" "{VARIANT}" biallelic phase confirmed
"{GENE}" "{VARIANT}" in trans "{DISEASE}"
"{GENE}" "{VARIANT}" parental testing phase
```

Same amino acid / PS1:

```text
"{GENE}" "{AMINO_ACID_CHANGE}" pathogenic
"{GENE}" "{SAME_AMINO_ACID_VARIANT}" "{DISEASE}"
"{GENE}" "{CODON}" same amino acid
"{GENE}" "{PROTEIN_POSITION}" nucleotide change same amino acid
```

Same residue / PM5:

```text
"{GENE}" "{RESIDUE}" different missense pathogenic
"{GENE}" "{PROTEIN_POSITION}" missense "{DISEASE}"
"{GENE}" "{RESIDUE}" same residue different amino acid
"{GENE}" "{PROTEIN_POSITION}" PM5
```

## `literature_records` JSON Fields

Recommended fields for each record:

```json
{
  "pmid": "11111111",
  "doi": "10.0000/example.1",
  "title": "Functional assessment of GENE1 c.76A>G in a disease model",
  "year": 2024,
  "journal": "Example Genetics",
  "gene": "GENE1",
  "variant": "NM_000001.1:c.76A>G",
  "disease": "GENE1-related example disorder",
  "extracted_claim": "The variant showed reduced activity in a validated assay with adequate controls.",
  "claim": "The variant showed reduced activity in a validated assay with adequate controls.",
  "evidence_type": "functional",
  "assay_validity": "validated",
  "de_novo_status": null,
  "segregation_count": null,
  "case_count": null,
  "trans_cis_status": null,
  "phenotype_match": "specific"
}
```

The `claim` field is included for compatibility with the current structured extraction path. Keep `extracted_claim` as the human-readable field from the literature workflow, and mirror it into `claim` when calling the MCP tool.

Evidence-type-specific fields may include:

- Functional evidence: `assay_validity`, `controls_adequate`, `functional_direction`.
- De novo evidence: `de_novo_status`, `confirmed_de_novo`, `parentage_confirmed`, `de_novo_reported`.
- Segregation evidence: `segregation_count`, `pedigree_context`.
- Case report / PS4 evidence: `case_count`, `multiple_unrelated_cases`, `case_control_enrichment`.
- Trans observation / PM3 evidence: `trans_cis_status`, `phase`, `confirmed_trans`.
- Same amino acid / PS1 evidence: `residue_relationship: "same_amino_acid"`.
- Same residue / PM5 evidence: `residue_relationship: "same_residue_different_missense"`.

## Manual Review Checklist

Before converting any suggestion to applied evidence, verify:

- Variant is completely identical, including transcript, nucleotide change, protein change, and genome build if relevant.
- Disease is the same condition or a justified equivalent in the same gene-disease mechanism.
- Functional assay is validated, disease-relevant, adequately controlled, and directionally interpretable.
- De novo status is confirmed, including parental testing and parentage where required.
- Segregation is countable from the pedigree and consistent with inheritance mode.
- Case reports are independent and not duplicated across publications, cohorts, families, or databases.
- Trans/cis status is explicit, with phase confirmed rather than inferred when PM3 is considered.
- PS1 and PM5 satisfy ACMG site-level definitions: same amino acid for PS1; same residue with a different missense change for PM5.

## Safety Statement

The literature workflow is decision support only.

- The Literature agent does not change classification.
- `suggested_evidence` is not `applied_evidence`.
- Outputs from `assess_literature_evidence` remain review notes until a qualified reviewer accepts and applies them through a separate reviewed-evidence process.
- Human review is required for every literature-derived ACMG criterion.
- The classification combiner must not be changed to consume literature suggestions automatically.

See also:

- `docs/ACMG_LITERATURE_AGENT.md`
- `docs/LITERATURE_AGENT_SAFETY.md`
- `examples/literature_agent_input.json`
- `examples/literature_agent_output.json`
