# Known Limitations

Variant Pathogenicity Rater v0.2.0-beta is an internal testing release. It does not
replace qualified clinical, laboratory, or genetics professional review.

## Scope

- Supports single and batch SNV/small-indel inputs only.
- Does not support CNV, SV, repeat expansion, mitochondrial, methylation,
  long-read, RNA-seq, exon-level deletion, or complex rearrangement evidence.
- HGVS-like normalization preserves unresolved fields when local parsing cannot
  resolve genomic coordinates. No liftover, transcript mapping service, or
  external normalization API is used.
- Transcript selection and annotation adapters provide review context only.
  They do not generate evidence or substitute for an explicitly supplied user
  transcript.
- Context consistency checks flag mismatched gene, transcript, disease,
  ancestry, inheritance, consequence, and genome-build context. They do not
  generate ACMG evidence and do not change the classification combiner.

## Evidence Boundaries

- ClinVar assertions do not directly apply PP5/BP6 and cannot determine
  classification by themselves.
- ClinVar-derived PS1/PM5 can be emitted only after independent comparator
  checks for protein consequence, nucleotide difference, transcript/protein
  context, disease/condition match, assertion quality, conflicts, germline
  applicability, and provenance. All generated PS1/PM5 requires review.
- ClinVar-derived PS1/PM5 remains limited by local protein parsing, conservative
  term-overlap condition matching, incomplete online ClinVar HGVS fields, lack
  of ontology/transcript mapping services, and no automatic VCEP-specific rule
  profiles.
- Literature-derived PS3, BS3, PS2, PM6, PP1, PS4, and PP4 hints are
  candidate-only and are not applied as strong evidence in this release.
- Manual reviewed evidence can apply curator-confirmed ACMG evidence, but only
  from explicit `reviewed_applied` records with curator rationale and
  provenance. Candidate evidence is never promoted silently.
- Computational PP3/BP4 automation is consensus-based and supporting-only. A
  single predictor, conflicting predictors, ambiguous calls, transcript mismatch,
  genome-build mismatch, or inappropriate consequence keeps evidence
  candidate-only or limitation-only.
- SpliceAI local-file results contribute only to computational evidence. They
  cannot trigger PS3, BS3, PVS1, RNA validation, or functional evidence and
  cannot upgrade PVS1.
- PM2 is currently capped at supporting strength. This intentional downgrade is
  part of the conservative prototype safety model.
- A local or mock provider miss means no matching record was found in that
  configured source. It does not mean the variant is absent from ClinVar,
  gnomAD, or any population database.
- Population BA1/BS1/PM2_Supporting automation requires high-quality provider
  data and complete disease-specific threshold context. Missing source version,
  low AN, low coverage, ancestry/population mismatch, genome-build mismatch,
  founder-population warnings, or context conflicts keep population evidence
  candidate-only or limitation-only.
- Provider records cannot automatically override user-provided context. A
  provider gene, transcript, condition, ancestry, or genome build mismatch is a
  review flag that must be resolved manually.
- VCEP profile support is a lightweight signal and limited override framework,
  not a full VCEP reasoning engine. Signals do not change classification, and
  approved overrides must be explicitly enabled, traceable, and limited to safe
  generator parameters or candidate-only downgrades.
- When disease context is missing, population and PVS1 confidence must not be
  elevated from the missing context. Population evidence remains candidate-only
  under missing disease-specific context, and PVS1 is not applied without
  disease context.
- Applied PVS1 is limited to SNV/small indel contexts with sufficient
  gene-disease, transcript, and NMD/splice information.
- Start-loss, stop-loss, uncertain splice effects, transcript mismatch,
  multiple transcript ambiguity, possible in-frame rescue, missing disease
  context, and unknown LoF mechanism are candidate-only by default.
- Canonical splice variants are not automatically treated as PVS1 Very Strong.
- Online LoF mechanism resolution is disabled by default; opt-in resolver
  failures are retained as limitations and never crash the pipeline.

## Reporting Boundaries

- Reports render the supplied `ClassificationResult`; they do not recalculate
  ACMG criteria, modify evidence strength, or change final classification.
- Candidate/review-note evidence is displayed separately from applied ACMG
  evidence. It should not be interpreted as counted evidence.
- `EvidenceItem.candidate_only` and `EvidenceItem.applied` are output/schema
  labels for the existing candidate/applied status; they do not authorize a
  candidate item to participate in classification.
- ClinVar and literature sections summarize external assertions or extracted
  claims for review. They are not automatically applied ACMG evidence.
- SpliceAI is computational splice prediction only. It is not functional
  evidence and does not by itself apply PS3, BS3, or PVS1.
- Transcript selection is recommendation/review-note context only, not evidence.
- Context consistency conflicts require manual review but are not classification
  changes.
- A VUS report means uncertainty. It must not be read as leaning pathogenic or
  benign without additional reviewed evidence and a qualified reviewer.

## Provider Boundaries

- The default data source mode is offline `mock`.
- Real provider validation is complete for the current ClinVar, gnomAD local
  snapshot, MANE transcript, and ClinGen ERepo provider surfaces, but this is
  validation of safe provider behavior, not clinical truth-set validation.
- Local fixtures and local snapshots are the primary validated provider path.
- Online ClinVar and ClinGen ERepo behavior is opt-in only and disabled by
  default. Online use requires explicit mode/config gates and must retain cache
  and provenance metadata.
- Online ClinVar, gnomAD, Ensembl VEP, PubMed, and LitVar providers are
  implemented and integration-reviewed as opt-in adapters, not default runtime
  dependencies.
- Local-file provider quality depends on the supplied local snapshot, genome
  build, parser compatibility, source freshness, and available provenance.
- Provider cache/provenance should preserve source or snapshot identity, query
  metadata, source version or live-source label, parser version, retrieval or
  snapshot time, raw-record or payload hash where available, and limitations.
- Provider failure, timeout, malformed payload, missing source version, stale
  source, missing provenance, provider miss, or context mismatch must become a
  structured limitation, review flag, failed record, or candidate-only output.
- Provider genome build is checked against input genome build when available.
  Mismatches are retained as context conflicts instead of being silently ignored.
- No provider directly changes classification. ClinVar/ERepo assertions,
  gnomAD frequency facts, and MANE/transcript metadata must pass through the
  existing evidence generators or manual reviewed-evidence workflow before they
  can affect applied evidence.
- ClinVar may support PS1/PM5 only as comparator facts after protein,
  nucleotide, transcript/protein, condition, germline, quality, conflict, and
  provenance gates pass.
- gnomAD/local population facts may support BA1/BS1/PM2_Supporting only through
  `population_rules` and configured thresholds. A provider miss or no local
  record is not population absence and must not trigger PM2 by itself.
- Ensembl VEP online facts may support PP3/BP4 only through the existing
  computational evaluator. Missing predictors are limitations, not direct
  PP3/BP4 evidence.
- PubMed/LitVar online records feed the General Literature Search and Summary
  Engine only as candidate/reviewed-draft literature inputs. They do not create
  applied evidence.
- MANE/RefSeq/Ensembl transcript metadata may support transcript, NMD, and PVS1
  context review, but cannot apply PVS1 or any other ACMG criterion by itself.
- ClinGen ERepo exact matches, VCEP activity signals, and supporting summaries
  remain review notes or reviewed-evidence drafts unless explicitly converted
  through valid curator-supplied `reviewed_applied` evidence.
- The latest documented full pytest result after 74 real provider pipeline
  integration review is `655 passed, 2 skipped`; live provider smoke tests are
  env-gated and skipped by default.

## Release Use

- Use this release for internal workflow testing, schema review, report review,
  and conservative regression checks.
- Do not use this release as an autonomous clinical interpretation system.
- Do not treat a machine proposal as a final assertion without manual review.
