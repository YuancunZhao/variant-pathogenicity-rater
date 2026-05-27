# VCEP Signal / Override Framework

The VCEP signal and override framework is a lightweight local profile layer for
ClinGen/VCEP gene- and disease-specific guidance. It is not a full VCEP
reasoning engine and does not import ClinGen Evidence Repository assertions as
applied ACMG evidence.

Current status: implemented and framework-validated. The implemented behavior
includes gene-level profile signals, approved profile overrides,
draft/provisional signal-only profiles, deprecated limitation-only profiles,
profile conflict blocking, report provenance, and per-record
`vcep_profile_summary` output for batch and annotated-batch workflows.

## Position In The Pipeline

The framework runs after variant normalization and gene-disease context
construction, before automatic evidence generators. It can produce:

- `VCEPSignalResult`: review context that VCEP/gene-specific guidance may
  exist.
- `VCEPOverrideContext`: an approved, non-conflicting, explicitly enabled set
  of narrow generator-parameter overrides.

Signals alone do not generate evidence, do not change evidence strength, and do
not change the final classification. Overrides are limited to existing
generator inputs and post-generator safety downgrades. The ACMG combiner remains
unchanged.

Approved overrides also cannot bypass generator safety gates. If the relevant
generator would block or downgrade evidence because of context, quality,
conflict, missing provenance, or unsupported scope, the VCEP override cannot
force that evidence to be applied.

## Runtime Options

VCEP behavior is off unless explicitly requested.

- `include_vcep_signals`: load and match local VCEP profiles as review context.
- `apply_vcep_overrides`: allow approved, non-conflicting profiles to apply the
  limited safe override set.
- `vcep_profile_records`: inline local profile records.
- `vcep_profile_file`: JSON or JSONL profile file.
- `vcep_kb_dir`: knowledge base directory containing `disease_profiles/`,
  `rule_overrides/`, and `vcep_signals/`.

CLI equivalents are `--include-vcep-signals`, `--apply-vcep-overrides`,
`--vcep-profile-file`, and `--vcep-kb-dir`.

## Safe Override Surface

Allowed v1 overrides:

- Population thresholds: replace configured BA1, BS1, or PM2 thresholds before
  population evidence generation.
- PVS1: disable PVS1, cap/downgrade maximum strength, or require focused
  review. No upgrade behavior is supported.
- Computational evidence: use stricter threshold values and add review notes.
  PP3/BP4 remain supporting-only.
- PS1/PM5: require candidate-only handling or add comparator review notes.
- Disabled criteria: convert generated criteria to candidate-only/review-note
  evidence before classification.
- Review flags: append review-required flags without changing evidence.

Overrides cannot create evidence by themselves, cannot make candidate evidence
applied, cannot bypass context or quality gates, and cannot modify the combiner.
Disabled criteria are not silently deleted; they remain visible as
candidate/review-note material with review flags and VCEP override provenance.

## Safety Gates

- No matching profile: generic ACMG behavior.
- Draft/provisional profile: signal only; no override.
- Deprecated profile: limitation only; no override.
- Multiple approved matching profiles: no override and a conflict review flag.
- Transcript mismatch against `applicable_transcripts`: no override.
- Missing disease or required inheritance context: no override.

Every affected evidence item must retain `supporting_data.vcep_override` with
profile id, version, citations, provenance, and whether the override was applied
to that item.

## Reporting

Reports include a separate `VCEP Signal / Rule Profile` section. This section is
outside Applied ACMG Evidence and states that VCEP signals alone were not counted
by the combiner. JSON reports expose the same payload as `vcep_profile`.

Batch and annotated-batch results preserve the same information per successful
record as `vcep_profile_summary`, so downstream review does not lose profile
signal, override, blocked, or limitation context.

## Recommended Next Validation

The next validation step is toy profile validation: small local profiles should
exercise approved override behavior, signal-only draft/provisional behavior,
deprecated limitation-only behavior, conflict blocking, disabled-criterion
candidate handling, report provenance, and batch/annotated-batch summaries.

After toy profile validation, the recommended track is real provider validation
for ClinVar, gnomAD, MANE, and ClinGen ERepo, benchmark expansion, a Chinese
report template, and one selected real VCEP profile pilot.
