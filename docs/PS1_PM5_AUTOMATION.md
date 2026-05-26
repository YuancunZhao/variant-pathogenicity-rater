# PS1/PM5 Automation

ClinVar-derived PS1/PM5 generation is a conservative comparator workflow. It
uses ClinVar records to identify previously asserted pathogenic/likely
pathogenic comparator variants, then independently checks protein, nucleotide,
transcript/protein, condition, assertion-quality, and provenance gates before
emitting any ACMG `EvidenceItem`.

ClinVar assertions alone do not become PP5 or BP6. All generated PS1/PM5
evidence requires qualified human review.

## Scope

The workflow is limited to SNV/small-indel records with parseable missense
protein consequences. It is intended for:

- PS1: same amino acid change caused by a different nucleotide change.
- PM5: different pathogenic missense change at the same residue.

It does not implement VCEP-specific rule profiles, external transcript mapping,
ontology services, functional evidence, segregation evidence, or clinical
sign-out.

## Decision Inputs

The generator consumes:

- The normalized query variant, including `hgvs_c`, `hgvs_p`, transcript, and
  genomic identity when available.
- Gene-disease context, especially disease/condition.
- ClinVar comparator records with clinical significance, review status,
  condition, germline/somatic status, HGVS, transcript/protein, and provenance.
- Context consistency results from the existing pipeline.

Provider gaps, parsing uncertainty, context conflicts, and missing source
metadata become limitations or candidate-only output.

## PS1 Gates

Applied PS1 requires all of the following:

- Query and comparator have parseable protein consequences.
- Same reference amino acid, residue position, and alternate amino acid.
- Different nucleotide or genomic change is confirmed.
- Comparator is not the same nucleotide/genomic variant.
- Transcript or protein accession matches.
- Disease/condition matches.
- ClinVar comparator is P/LP, germline applicable, not conflicting, and
  high-quality for applied use.

If the same amino acid change is present but the nucleotide difference cannot be
confirmed, PS1 remains candidate-only. If the comparator is the same variant,
PS1 is blocked.

## PM5 Gates

Applied PM5 requires all of the following:

- Query and comparator are parseable missense changes.
- Same reference amino acid and same residue position.
- Different alternate amino acid.
- Transcript or protein accession matches.
- Disease/condition matches.
- ClinVar comparator is P/LP, germline applicable, not conflicting, and
  high-quality for applied use.

Same residue alone is insufficient. The same amino acid change is not PM5; it is
handled by the PS1 path if the nucleotide-change gate is satisfied.

## ClinVar Confidence

Applied PS1/PM5 requires a high-quality ClinVar comparator, such as an expert
panel/practice guideline assertion or multiple submitters with no conflicts.

The following block or downgrade applied evidence:

- Conflicting interpretations or conflict status: blocks applied evidence.
- Somatic-only applicability: blocks germline applied evidence.
- Single submitter, no assertion criteria, zero/one star, or missing review
  status: candidate-only.
- Non-P/LP significance: unavailable for PS1/PM5.

ClinVar P/LP assertions never become automatic PP5 evidence.

## Condition Matching

Disease/condition context is required. Applied evidence requires exact or strong
normalized term overlap between the query disease and ClinVar condition. Missing,
ambiguous, or mismatched condition blocks applied PS1/PM5.

The current implementation does not use an ontology service, so condition
matching remains conservative.

## Output Semantics

Applied output is emitted as a normal `EvidenceItem` before the existing
combiner runs:

- PS1: `strength=strong`, `direction=pathogenic`.
- PM5: `strength=moderate`, `direction=pathogenic`.
- `requires_review=true`.
- `supporting_data.not_pp5=true`.

Candidate output uses:

- `strength=none`.
- `candidate_only=true`.
- `applied=false`.
- `supporting_data.evidence_status="candidate"`.

Candidate PS1/PM5 records are reportable review notes only and must not affect
classification.

## Provenance

Each generated item preserves:

- ClinVar source name, version, database ID, retrieval timestamp, query, and raw
  snapshot reference when available.
- Comparator `variation_id`, clinical significance, review status, review stars,
  submitter count, condition, and germline/somatic status.
- Query/comparator protein and nucleotide comparison details.
- Decision path, quality checks, blocking reasons, downgrade reasons, and
  limitations.

## Examples

- Applied PS1: `p.Lys26Arg` query and high-quality ClinVar P/LP comparator
  `p.Lys26Arg`, same transcript/protein, same disease, different `hgvs_c`.
- Candidate PM5: `p.Lys26Arg` query and same-residue comparator `p.Lys26Asn`,
  but ClinVar assertion is single-submitter.
- Blocked PS1/PM5: comparator condition is unrelated to the query disease, or
  comparator has conflicting ClinVar interpretations.
