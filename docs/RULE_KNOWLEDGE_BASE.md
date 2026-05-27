# Rule Knowledge Base

The rule knowledge base stores local, versioned ClinGen/VCEP profile records
used by the VCEP signal and override framework.

## Directory Layout

```text
knowledge_base/
  vcep_signals/
  rule_overrides/
  disease_profiles/
```

Current runtime loading accepts JSON and JSONL profile records from a direct
profile file or from these directories. Profile records in all three directories
are validated with the same lightweight schema; future work may add reusable
override fragments.

## Profile Schema

Required identity and governance fields:

- `profile_id`
- `gene`
- `disease`
- `inheritance`
- `vcep_name`
- `source`
- `version`
- `status`: `approved`, `provisional`, `draft`, or `deprecated`
- `effective_date`
- `citations`
- `provenance`

Profile behavior fields:

- `applicable_transcripts`
- `rule_signals`
- `population_threshold_overrides`
- `pvs1_overrides`
- `computational_overrides`
- `ps1_pm5_overrides`
- `disabled_criteria`
- `review_required_flags`
- `notes`

## Authoring Rules

- Use `approved` only for profiles that are reviewed enough to alter generator
  parameters under explicit runtime enablement.
- Use `draft` or `provisional` for signal-only profiles.
- Use `deprecated` when guidance should be visible as a limitation but not
  applied.
- Keep profile scope narrow: gene, disease, inheritance, transcripts, source,
  version, and effective date must be explicit.
- Do not encode full VCEP reasoning, functional evidence application, family
  evidence, case-control logic, or manual clinical judgment.

## Provenance Requirements

Each profile should include citations and source metadata sufficient for a
reviewer to identify the guidance version. When an override affects generated
evidence, the evidence item records profile id, version, citations, provenance,
and override notes in `supporting_data.vcep_override`.
