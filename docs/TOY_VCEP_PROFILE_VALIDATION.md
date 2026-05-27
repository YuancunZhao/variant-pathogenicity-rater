# Toy VCEP Profile Validation

Toy VCEP profiles validate the local VCEP signal and override framework without
encoding real ClinGen or VCEP rules. They are deliberately small, synthetic
fixtures for framework behavior only.

These profiles live under:

`knowledge_base/rule_overrides/toy/`

Every toy profile is marked `TOY PROFILE - TESTING/DEMO ONLY - NOT REAL
CLINGEN/VCEP GUIDANCE` in the profile source and carries toy provenance. They
must not be used for clinical interpretation, production runs, or benchmark
claims about real VCEP specifications.

## Purpose

The toy profile set exercises the safe override surface before a real VCEP
profile pilot:

- population threshold override
- PVS1 disabled behavior
- stricter computational threshold note
- PS1/PM5 candidate-only behavior
- disabled criterion candidate/review-note handling
- draft profile signal-only behavior
- provisional profile signal-only behavior
- deprecated profile limitation-only behavior
- conflicting approved profile blocking

The goal is to prove the framework wiring, provenance, report output, batch
summary preservation, and safety gates. The toy profiles do not validate any
real gene-specific thresholds, disease-specific assumptions, transcript rules,
or ClinGen/VCEP evidence logic.

## Loading Rules

VCEP behavior remains off unless explicitly requested. Toy profiles are placed
in a nested `rule_overrides/toy/` directory so the normal `vcep_kb_dir`
top-level scan does not load them as production KB records.

Tests load toy profiles by explicit file path:

```python
options = {
    "include_vcep_signals": True,
    "apply_vcep_overrides": True,
    "vcep_profile_file": "knowledge_base/rule_overrides/toy/brca1_population_override.approved.json",
}
```

Do not add toy profile files directly under `knowledge_base/rule_overrides/`,
`knowledge_base/disease_profiles/`, or `knowledge_base/vcep_signals/`. Doing so
would make them eligible for a normal KB directory load.

## What Is Validated

`tests/test_toy_vcep_profile_validation.py` validates that:

- toy population threshold overrides can change the generator threshold but
  still respect population quality gates
- toy PVS1 disable converts an applied PVS1 item to candidate/review-note
  evidence
- toy computational stricter thresholds do not create applied evidence by
  themselves
- toy PS1/PM5 candidate-only overrides block applied PS1/PM5 evidence
- toy disabled criteria remain visible as review-note evidence with blocking
  context instead of being silently deleted
- draft and provisional toy profiles remain signal-only even when overrides are
  requested
- deprecated toy profiles produce limitations only
- conflicting approved toy profiles block override application
- reports and provenance show toy profile origin
- batch and annotated-batch results preserve `vcep_profile_summary`
- signal-only toy use does not change classification combiner behavior

Run the validation with:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache .venv/bin/python -m pytest tests/test_toy_vcep_profile_validation.py
```

## Safety Boundaries

Toy profiles must not:

- implement real ClinGen/VCEP criteria
- modify or bypass the ACMG classification combiner
- relax existing quality, context, transcript, or conflict safety gates
- create evidence independently of an existing generator
- silently remove disabled evidence
- be loaded by default production KB configuration

The framework can only pass profile information into existing generator
parameters or convert generated items to candidate/review-note evidence. The
combiner consumes the resulting evidence status exactly as before.

## Migrating To A Real VCEP Profile Pilot

Use the toy validation suite as the framework checklist, then replace synthetic
profiles with a narrowly scoped real pilot:

1. Select one VCEP/gene/disease pair and document the source guideline,
   version, effective date, citations, transcript scope, and disease scope.
2. Encode only rule behavior that maps to the existing safe override surface.
   Do not add new combiner semantics.
3. Add explicit provenance and review-required flags for every pilot override.
4. Add tests mirroring the toy suite with real profile fixtures and curated
   expected behavior.
5. Confirm that draft, provisional, deprecated, transcript-mismatch, missing
   context, and multi-profile conflict safety behavior remains unchanged.
6. Run full pytest and compare report, provenance, batch, and annotated-batch
   outputs before enabling the pilot path for any workflow.

Real VCEP profile files should live outside the toy directory and should only
be loaded through an explicit reviewed KB path once validated.
