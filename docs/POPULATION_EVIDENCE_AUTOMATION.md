# Population Evidence Automation

Population evidence generation lives in `variant_pathogenicity_rater.population`.
It wraps the existing `acmg.population_rules` implementation with an additional
decision layer for BA1, BS1, and PM2_Supporting. The ACMG combiner is unchanged.

## Applied Conditions

BA1 and BS1 are applied only when all of these are true:

- A usable population AF is present.
- The AF meets the configured BA1 or BS1 threshold.
- Thresholds are marked disease-specific and penetrance context is provided.
- Disease, inheritance, and prevalence context are complete.
- Allele number, coverage, population match, ancestry match, genome build, source
  version, provider confidence flags, founder-population checks, and context
  consistency all pass.

PM2_Supporting is applied only when all of these are true:

- AF is truly zero or very low in a usable matched record.
- Allele number is sufficient and coverage is adequate.
- Population and ancestry context match.
- Genome build matches the normalized variant.
- Source version/provenance is retained.
- Disease context is complete and thresholds are disease-specific.
- No context conflict, founder warning, low-confidence provider flag, low AN, or
  low coverage warning is present.

All generated population evidence sets `requires_review=true`.

## Candidate-Only Conditions

The generator emits candidate-only evidence when the AF threshold points toward
BA1, BS1, or PM2_Supporting but any safety gate fails. Candidate items have
`applied=false`, `candidate_only=true`, and `strength=none`, so they are excluded
from the combiner.

Candidate-only downgrades include:

- Missing disease-specific threshold or penetrance context.
- Missing disease prevalence or inheritance.
- Low allele number or low coverage.
- Population or ancestry mismatch.
- Genome build mismatch.
- Missing source version.
- Low-confidence provider flags.
- Founder-population warning.
- Context consistency conflict.

## No Record Found

No record found is not population absence. A provider miss, unusable AF, malformed
record, or local-file miss does not trigger PM2_Supporting. The decision is kept
as a limitation and decision-path entry rather than ACMG evidence.

## Decision Payload

Each generated EvidenceItem includes `supporting_data.population_evidence_decision`
with:

- recommended code, strength, direction, applied/candidate status
- decision path
- thresholds used
- quality checks
- blocking and downgrade reasons
- limitations
- provenance

Reports render the AF/threshold rationale and population decision path without
recalculating classification.

## Human Review Checklist

- Confirm the variant and population record are on the same genome build.
- Confirm AF, allele number, coverage, and source version from the provider.
- Confirm the population is ancestry matched and not a founder-population artifact.
- Confirm disease prevalence, penetrance, inheritance, and threshold source.
- Confirm no context consistency conflict remains unresolved.
- Confirm candidate-only population evidence was not counted in classification.
