# Known Limitations

Variant Pathogenicity Rater v0.1.0 is an internal testing prototype. It does not
replace qualified clinical, laboratory, or genetics professional review.

## Scope

- Supports single SNV and small-indel inputs only.
- Does not support CNV, SV, repeat expansion, mitochondrial, methylation,
  long-read, RNA-seq, exon-level deletion, or complex rearrangement evidence.
- HGVS-like normalization preserves unresolved fields when local parsing cannot
  resolve genomic coordinates. No liftover, transcript mapping service, or
  external normalization API is used.

## Evidence Boundaries

- ClinVar assertions are candidate/review-note only. They do not directly apply
  ACMG criteria and do not trigger PP5/BP6.
- ClinVar candidate records can flag possible PS1/PM5-style review questions,
  but independent variant/protein-level assessment is required.
- Literature-derived PS3, BS3, PS2, PM6, PP1, PS4, and PP4 hints are
  candidate-only and are not applied as strong evidence in this release.
- SpliceAI local-file results contribute only to computational evidence. They
  cannot trigger PS3, BS3, or PVS1 and cannot upgrade PVS1.
- PM2 is currently capped at supporting strength. This intentional downgrade is
  part of the conservative prototype safety model.
- A local or mock provider miss means no matching record was found in that
  configured source. It does not mean the variant is absent from ClinVar,
  gnomAD, or any population database.

## Provider Boundaries

- The default data source mode is offline `mock`.
- Online ClinVar is opt-in only and requires both `mode=online` or
  `future_online` and `online_enabled=true`.
- Population, literature, and computational online providers are not
  implemented for v0.1.0.
- Local-file provider quality depends on the supplied local snapshot, genome
  build, parser compatibility, and source freshness.

## Release Use

- Use this release for internal workflow testing, schema review, report review,
  and conservative regression checks.
- Do not use this release as an autonomous clinical interpretation system.
- Do not treat a machine proposal as a final assertion without manual review.

