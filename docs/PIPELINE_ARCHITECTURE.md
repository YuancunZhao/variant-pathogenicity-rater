# Pipeline Architecture

## Purpose

This document is the high-level architecture reference for the current
single-variant pipeline after the 81A-3 phase decomposition.

`rate_variant.py` is now an orchestration layer. Business logic should live in
the appropriate phase module unless it is strictly orchestration logic.

## Current Pipeline

```text
rate_variant
  -> normalization_phase
  -> resolution_phase
  -> provider_phase
  -> evidence_phase
  -> classification_phase
  -> output_phase
```

## Responsibilities

### rate_variant.py

`rate_variant.py` preserves the public `rate_variant(arguments)` API and
coordinates phase execution. It owns shared audit/step execution plumbing and
passes phase outputs to later phases.

Do not add new business logic here unless it is orchestration-only.

### normalization_phase.py

`normalization_phase` performs variant normalization and initial gene-disease
context bootstrap. It preserves normalization warnings, normalization
`step_results`, and normalization-failure handling through the existing output
path.

### resolution_phase.py

`resolution_phase` performs variant resolution and updates the current
normalized variant/context when resolution provides a better representation.
Resolution facts remain descriptive context unless later evidence-generation
rules explicitly use them.

### provider_phase.py

`provider_phase` prepares provider identity from normalized and resolved variant
state. It does not query providers and does not generate evidence.

### evidence_phase.py

`evidence_phase` executes provider queries, dependency skips, VCEP signal and
override handling, transcript selection/validation, context consistency checks,
applied evidence generation, candidate/review-note collection, reviewed
evidence integration, and evidence-combine bookkeeping.

This phase preserves the existing applied/candidate/review-note boundaries.
Provider facts remain provider facts unless an existing conservative evidence
generator emits applied evidence.

### classification_phase.py

`classification_phase` calls the ACMG combiner with the accumulated evidence
items and normalized context. It also attaches phase-level review flags and
classification view context.

It must not generate new evidence or reinterpret provider records.

### output_phase.py

`output_phase` generates reports, serializes provider runtime results,
constructs `provider_mode_summary`, assembles legacy top-level output fields,
and applies the canonical output schema.

Output generation is presentation and serialization work. It must not change
final classification or evidence generation.

## Extension Guidelines

Future features should be added to the phase that owns their behavior:

- normalization changes belong in `normalization_phase` or normalization
  modules.
- descriptive resolution changes belong in `resolution_phase` or resolution
  modules.
- provider identity preparation belongs in `provider_phase`.
- provider queries, evidence generation, reviewed evidence integration, and
  evidence status preservation belong in `evidence_phase` or specialized
  evidence/provider modules called by that phase.
- classification post-processing belongs in `classification_phase`.
- report, provider runtime serialization, legacy output assembly, and canonical
  schema work belong in `output_phase`.

Avoid adding new business logic directly to `rate_variant.py` unless it is
strict orchestration logic.

## Safety Boundaries

The following boundaries should remain isolated:

- `acmg/combiner.py`
- evidence generation
- reviewed evidence validation
- population ACMG rules
- computational ACMG rules

Pipeline phase changes must preserve:

- final classification behavior
- evidence generation behavior
- applied/candidate/review-note separation
- public API compatibility
- legacy output fields
- default offline behavior
