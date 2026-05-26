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

## Population Layer

Population evidence generation lives in `variant_pathogenicity_rater.population`.
It adds a conservative decision layer around the existing
`acmg.population_rules` BA1/BS1/PM2 implementation. The combiner is unchanged:
candidate-only population evidence is excluded, and applied population evidence
affects classification only after it is emitted as a normal `EvidenceItem`.

Population decisions require high-quality provider data, disease-specific
threshold context, penetrance context, matched ancestry/population, matching
genome build, source version, adequate allele number and coverage, and no context
conflict. BA1/BS1 may be applied only with configured disease-specific
thresholds. PM2 is capped at supporting strength and cannot be triggered from a
provider miss or "no record found" result.

See [POPULATION_EVIDENCE_AUTOMATION.md](POPULATION_EVIDENCE_AUTOMATION.md).

## Computational Layer

Computational evidence generation lives in `variant_pathogenicity_rater.computational`.
It produces PP3/BP4 `EvidenceItem` records from calibrated predictor consensus
without changing the classification combiner.

PP3/BP4 are capped at supporting strength, always require review, and are
candidate-only unless multiple calibrated predictors agree and safety gates pass.
Candidate computational evidence is retained for reporting but is excluded from
classification by the existing candidate-only combiner behavior.

Predictor conflict blocks applied PP3/BP4. SpliceAI contributes only
computational splice support; it is not functional evidence, RNA validation, PS3,
BS3, or PVS1 evidence. See
[COMPUTATIONAL_EVIDENCE_AUTOMATION.md](COMPUTATIONAL_EVIDENCE_AUTOMATION.md).

Frameshift, nonsense, CNV, and SV contexts generally do not receive applied
computational evidence from missense predictors. Such calls are retained only as
candidate/review-note evidence or limitations so LoF mechanisms are not double
counted through PP3.

## ClinVar-Derived PS1/PM5 Layer

ClinVar-derived PS1/PM5 generation lives in
`variant_pathogenicity_rater.ps1_pm5`. It uses ClinVar only as a comparator
source for previously asserted pathogenic/likely pathogenic variants; ClinVar
assertions do not become PP5/BP6 evidence.

Applied PS1 requires a same amino acid change caused by a confirmed different
nucleotide/genomic change, matched transcript/protein context, matched disease
condition, high-quality non-conflicting germline ClinVar P/LP comparator, and
preserved provenance. Applied PM5 requires a different missense change at the
same residue under the same context and quality gates.

Missing or unparseable protein consequence, low-quality ClinVar assertion,
unresolved nucleotide difference, transcript/protein uncertainty, or provider
gaps keep output candidate-only. ClinVar conflicts, condition mismatch, context
conflicts, somatic-only assertions, and same-variant comparisons block applied
PS1/PM5.

See [PS1_PM5_AUTOMATION.md](PS1_PM5_AUTOMATION.md).

## Source Priority

LoF mechanism priority is manual/context override, local curated table, optional online resolver with cache and provenance, then unknown. ClinVar P/LP assertions are not used as LoF mechanism evidence.

## Safety Contract

- PVS1 is not applied from frameshift, stop-gained, or canonical splice terms alone.
- Candidate-only evidence does not participate in classification.
- All PVS1 evidence requires manual review.
- All generated population evidence requires manual review.
- All generated computational evidence requires manual review.
- All generated PS1/PM5 evidence requires manual review.
- ClinVar assertions alone do not trigger PP5/BP6.
- ClinVar conflicts and condition mismatch block applied PS1/PM5.
- PP3/BP4 remain supporting-only and cannot be applied from one predictor.
- PP3 and BP4 cannot both be applied from computational predictions.
- SpliceAI cannot trigger PS3, BS3, or PVS1.
- Online failure is a limitation only.
- VCEP-specific overrides are reserved for a future extension.
