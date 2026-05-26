# Computational Evidence Automation

Phase 3 generates conservative PP3/BP4 evidence from computational prediction
providers. It does not change the ACMG classification combiner.

## Applied Conditions

PP3 and BP4 can only be emitted at `supporting` strength and always set
`requires_review=true`.

Applied PP3 requires:

- variant context appropriate for the predictor group;
- at least two calibrated predictors supporting deleterious effect;
- majority agreement with no opposing benign predictor conflict;
- adequate source quality and matching transcript/genome build when supplied;
- no major context consistency conflict;
- no same-mechanism double counting with applied PVS1.

Applied BP4 requires:

- at least two calibrated predictors supporting benign/no effect;
- no pathogenic predictor conflict;
- variant context appropriate for the predictor group;
- no high-impact/splice warning that blocks benign computational use.

## Consensus Strategy

Predictors are parallel inputs. REVEL, CADD, SIFT, PolyPhen, MutationTaster,
AlphaMissense, SpliceAI, and placeholders such as dbscSNV are calibrated into
directional calls and then counted by group. No predictor can override the
others, and no single predictor can apply PP3 or BP4.

The decision layer also evaluates an overall countable consensus across groups
so independent predictors can support the same direction without one method
overriding another. Opposite directions across groups are treated as predictor
conflict and block applied evidence.

Predictor groups:

- missense: REVEL, CADD, SIFT, PolyPhen, MutationTaster, AlphaMissense
- splice: SpliceAI, dbscSNV placeholder
- future placeholders: conservation and meta predictors

Conflicting pathogenic and benign calls block applied evidence. The decision is
reported as candidate-only or limitation-only with review flags.

## SpliceAI Boundaries

SpliceAI is computational splice prediction only. A high delta score can support
PP3 at supporting strength when other gates pass. A low score cannot apply BP4
alone. Transcript or genome-build mismatch keeps the evidence candidate-only.

SpliceAI never triggers PS3, BS3, PVS1, or RNA-validation evidence. Canonical
splice plus high SpliceAI is still computational support only. If applied PVS1 is
already present for the same possible LoF/splice mechanism, the generator emits a
double-counting warning and keeps splice computational PP3 candidate-only.

## Providers

Local-file providers support JSON, JSONL, and TSV snapshots. Flat records may
include `gene`, `transcript`, `hgvs_p`, `protein_change`, `revel_score`,
`cadd_score`, `sift_prediction`, `polyphen_prediction`,
`mutationtaster_prediction`, `alphamissense_score`, `alphamissense_class`,
`spliceai_delta_score`, `source_version`, `genome_build`, and `provenance`.
JSON inputs may be an array, a `{ "records": [...] }` object, or a single record
object.

Online computational providers are placeholders, disabled by default. Failures
must be recorded as limitations and must not change classification.

## Human Review Checklist

- Confirm variant, transcript, protein change, and genome build match.
- Confirm consequence is appropriate for the predictor group.
- Review all conflicting or ambiguous predictors.
- Confirm PP3 and BP4 are not both applied.
- Confirm computational prediction is not being treated as functional or RNA
  evidence.
- Check for PVS1 or other same-mechanism double counting.
