# Transcript Selection Framework

The transcript selection layer recommends an annotation transcript for human review. It is a
descriptive review aid only: it does not trigger ACMG criteria, does not change the classification
combiner, and does not replace a transcript explicitly supplied by the user.

## Output Contract

`TranscriptSelection` records:

- `selected_transcript` and `selected_gene`
- `selection_reason` and `selection_confidence`
- `candidate_transcripts` and `rejected_transcripts`
- availability of MANE Select, canonical, and biologically relevant transcripts
- whether a user transcript was provided and whether it matched annotation records
- `review_flags`, `limitations`, and selector `provenance`

If no annotation records are available, the selector returns no selected transcript and records a
limitation. The pipeline can continue because transcript selection is optional metadata.

## Selection Principles

The selector applies conservative offline priorities:

1. Preserve a user-provided transcript when it matches annotation records.
2. If the user transcript does not match, do not substitute another transcript automatically.
3. Prefer MANE Select when present.
4. Prefer clinically or biologically relevant annotations when marked by the annotation source.
5. Use canonical transcript as a fallback.
6. Prefer protein-coding transcripts.
7. Use more severe consequence only as a tie-breaker, and flag it for review.

Multiple candidates at the same priority are flagged as transcript ambiguity. Ambiguity always
requires human review.

## MANE And Canonical Limits

MANE Select and canonical tags are useful transcript-selection metadata, but they are not clinical
assertions. They can disagree, be absent, or appear on multiple records depending on annotation
source, transcript version, genome build, and parser behavior. Conflicting MANE or canonical tags
therefore produce review flags rather than evidence.

## Not ACMG Evidence

Transcript selection is intentionally separated from ACMG evidence evaluation. A selected transcript
does not mean PVS1, PP3, BP4, or any other ACMG criterion is met. In particular, PVS1 must not be
upgraded because selection recommended a transcript. Evidence modules must evaluate their own
criteria from their explicit inputs, and the classification combiner only combines supplied
`EvidenceItem` records.

## Mandatory Human Review

Human review is required when:

- the user-provided transcript is absent from annotation records
- multiple transcripts have equal priority
- multiple MANE Select or canonical transcripts are present
- a non-coding transcript is selected
- no transcript identifier is available
- no annotation records are available
- a more severe consequence was used as a tie-breaker
- annotation sources disagree about gene, transcript, consequence, or transcript tags

Reports display the transcript selection summary as recommendation/review-note only and state that
it is not ACMG evidence.
