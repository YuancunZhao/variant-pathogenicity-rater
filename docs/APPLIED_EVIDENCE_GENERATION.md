# Applied Evidence Generation

Applied evidence generation creates ACMG `EvidenceItem` records before the classification combiner runs. The combiner remains unchanged and only combines evidence it is given.

## PVS1 Layer

The PVS1 generation layer lives in `variant_pathogenicity_rater.pvs1`:

- `consequence.py`: consequence and HGVS LoF parsing.
- `lof_mechanism.py`: manual, local-curated, then optional-online LoF mechanism resolution.
- `transcript.py`: transcript relevance checks.
- `nmd.py`: NMD and terminal-exon assessment.
- `splice.py`: splice-specific PVS1 path.
- `decision_tree.py`: conservative decision tree and downgrades.
- `applied_generator.py`: conversion into `EvidenceItem` records.

## Source Priority

LoF mechanism priority is manual/context override, local curated table, optional online resolver with cache and provenance, then unknown. ClinVar P/LP assertions are not used as LoF mechanism evidence.

## Safety Contract

- PVS1 is not applied from frameshift, stop-gained, or canonical splice terms alone.
- Candidate-only evidence does not participate in classification.
- All PVS1 evidence requires manual review.
- Online failure is a limitation only.
- VCEP-specific overrides are reserved for a future extension.
