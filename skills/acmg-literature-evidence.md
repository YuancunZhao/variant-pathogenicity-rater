# ACMG Literature Evidence Agent Skill

Use this skill for optional, non-invasive ACMG literature evidence assessment. The output is `suggested_evidence` only. It must never be copied into `applied_evidence` automatically and must never change final classification.

## Retrieval Strategy

- Start offline with caller-provided `literature_records`, PMIDs, citations, abstracts, or extracted snippets.
- If online search is explicitly requested, mark it as opt-in and preserve search provenance. If retrieval fails, return limitations rather than failing the whole assessment.
- Query by exact variant first: gene + HGVS c., gene + HGVS p., transcript + HGVS, rsID when available.
- Then query gene + disease + phenotype, and only then broader gene + variant residue terms.
- Deduplicate by PMID, DOI, study cohort, family, and case series before counting cases or segregations.

## PubMed / LitVar Query Patterns

- `GENE AND "c.xxx"`, `GENE AND "p.Xxx123Yyy"`, `TRANSCRIPT AND c.xxx`.
- `GENE AND DISEASE AND variant`.
- `GENE AND (functional assay OR activity OR expression OR localization)`.
- `GENE AND (de novo OR parentage OR trio)`.
- `GENE AND (segregation OR pedigree OR family)`.
- `GENE AND (compound heterozygous OR in trans OR phase)`.

## Functional Assay Checklist

- Assay validity is explicitly described.
- Positive and negative controls are adequate.
- Functional direction is clear and disease mechanism is compatible.
- Variant, transcript, gene, disease, and assay context match.
- If any of these are missing, keep PS3/BS3 as candidate-only.

## Segregation Checklist

- Count informative segregations.
- Confirm pedigree context and affected/unaffected status.
- Avoid duplicate families across publications.
- Keep PP1 candidate-only if count or pedigree context is unclear.

## De Novo Checklist

- PS2 requires confirmed de novo status and confirmed parentage.
- PM6 may be suggested for unconfirmed de novo reports.
- If de novo language is ambiguous, keep candidate-only.

## Phenotype Specificity Checklist

- Confirm phenotype is highly specific for the gene/disease pair.
- Confirm disease mechanism and inheritance fit.
- PP4 remains review-only and must not independently drive classification.

## PS1 / PM5 Residue-Level Checklist

- PS1: same amino acid change as a known pathogenic variant.
- PM5: same residue, different missense change.
- Same codon is not automatically same amino acid.
- Nearby residue is not PS1 or PM5 without additional manual review.

## Suggestion Rules

- Supported codes: PS3, BS3, PS2, PM6, PP1, PS4, PP4, PM3, PS1, PM5.
- Every suggested item must include citation, extracted claims, confidence, limitations, and provenance.
- Every suggested item must set `requires_manual_review=true`.
- Every suggested item must include a reason it was not automatically applied.

## Prohibited Behavior

- Do not write to `applied_evidence`.
- Do not invoke or modify the ACMG combiner.
- Do not change final classification wording.
- Do not loosen safety gates because literature appears persuasive.
- Do not treat transcript selection, context consistency, or raw literature retrieval as ACMG evidence.

## JSON Output

Return:

```json
{
  "literature_evidence_assessments": [],
  "suggested_evidence": [],
  "review_questions": [],
  "citations": [],
  "limitations": [],
  "provenance": {}
}
```
