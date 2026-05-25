# PVS1 Automation

Variant Pathogenicity Rater includes an applied PVS1 generation layer for SNV and small indel variants. It follows a conservative ClinGen SVI decision-tree style workflow rather than triggering PVS1 from a consequence term alone.

## Supported Scope

- Frameshift, stop-gained, canonical splice donor/acceptor, start-lost, stop-lost, and exon-loss placeholder consequences.
- Transcript relevance checks using user transcript, MANE Select, canonical status, protein-coding biotype, and transcript-selection summaries.
- NMD and terminal-exon downgrading when explicit context or exon annotations are present.
- Splice-specific candidate or downgraded paths for canonical splice variants, predicted exon skipping, in-frame rescue, and RNA-supported placeholders.

CNV, SV, exon-level deletion, complex rearrangement, DMD reading-frame-specific SV logic, and VCEP-specific overrides are not automated in this phase.

## Applied Conditions

Applied PVS1 is generated only when the LoF consequence is clear, gene/disease/inheritance context is present, LoF is a known mechanism for the gene-disease pair, the transcript is relevant and protein coding, NMD or splice logic supports the strength, and no conflict or rescue risk blocks application.

All PVS1 evidence has `requires_review=true` and `supporting_data.requires_manual_review=true`.

## Candidate-Only Scenarios

PVS1 is candidate/review-note only when disease context is missing, LoF mechanism is unknown, transcript relevance is unclear, multiple transcripts are ambiguous, NMD is unavailable for a high-strength path, splice consequence is uncertain, start-loss or stop-loss lacks explicit review support, or in-frame rescue is possible.

Candidate PVS1 has `candidate_only=true`, `applied=false`, and strength `none`; the existing combiner excludes it.

## Decision Path

The decision object records consequence, LoF mechanism, transcript relevance, NMD/exon position, splice path, rescue risk, context conflicts, final strength, downgrade reasons, blocking reasons, limitations, and provenance. Reports display the PVS1 decision path for manual review.

## Online Behavior

Offline/mock mode is the default. Optional online LoF mechanism resolution is opt-in through `pvs1_config.enable_online_resolvers=true`. Online resolver output is cached with provenance. Failures are recorded as limitations and never crash the pipeline.
