# Literature Agent Safety Framework

This framework prepares Variant Pathogenicity Rater for future PubMed/LitVar-assisted evidence extraction while keeping all literature-derived evidence candidate-only. The current implementation is offline by design: it uses mock records or local JSON/JSONL files only and does not include a real PubMed, LitVar, or full-text API client.

## Safety Position

Literature evidence is noisy, context-dependent, and often ambiguous without expert review of the full paper, assay validation, cohort independence, phenotype fit, and disease mechanism. For that reason, every literature-derived item is stored as candidate/review-note evidence and is never allowed to alter the final ACMG classification.

The report generator displays literature candidates under `Candidate / Review-Note Evidence`. They do not enter `Applied ACMG Evidence`, and the ACMG combiner ignores them because they are emitted with `strength=none`, `candidate_only=true`, and `automatic_application=false`.

## Candidate Schema

Each extracted claim preserves citation and provenance and records:

- `article_id`
- `title`
- `journal`
- `year`
- `pmid` / `doi`
- `extracted_claim`
- `evidence_type_candidate`
- `evidence_quality`
- `assay_type`
- `phenotype_match`
- `condition_match`
- `variant_match_level`
- `duplicate_study_group`
- `extraction_confidence`
- `requires_manual_review`

Allowed candidate evidence labels are:

- `PS3_candidate`
- `BS3_candidate`
- `PS2_candidate`
- `PM6_candidate`
- `PP1_candidate`
- `PS4_candidate`
- `PP4_candidate`

## Non-Automated ACMG Items

The literature agent must not automatically trigger or strengthen:

- `PS3` or `BS3` from functional assays
- `PP1` from segregation reports
- `PS4` from case reports, case series, or case-control claims
- `PS2` or `PM6` from de novo reports
- `PP4` from phenotype similarity or specificity claims

Variant mismatch, condition mismatch, phenotype mismatch, and low extraction confidence always create blocking review flags. Duplicate publications or overlapping cohorts should share `duplicate_study_group`; the local provider collapses that group before mapping candidate evidence so the same study cannot be counted twice.

## Manual Review Guidance

For `PS3` / `BS3`, a reviewer should confirm assay validity, disease mechanism relevance, controls, replication, calibration against known pathogenic/benign variants, and whether the assayed construct exactly matches the interpreted variant.

For `PP1`, a reviewer should verify the pedigree, affected status, genotype data, phenocopies, recombination, mode of inheritance, and that multiple reports are not the same family.

For `PS4`, a reviewer should confirm case independence, ancestry/population background, ascertainment, case-control enrichment, statistical support, and whether the paper reports the same condition and exact variant.

For `PS2` / `PM6`, a reviewer should verify maternity/paternity confirmation, phenotype specificity, mosaicism details, sample identity, and whether the reported event is truly the interpreted variant in the relevant disease.

For `PP4`, a reviewer should verify that the phenotype is highly specific for the gene-disease association and that the assertion is not merely a broad similarity statement.

## Local-File Provider

Local literature mode accepts JSON or JSONL records. It can match by gene, HGVS c., HGVS p., genomic coordinates, or PMID. This mode is intended for curated snapshots, benchmark fixtures, and smoke tests. It performs no network access.

## Future PubMed/LitVar Plan

Future online integration should be added behind explicit opt-in configuration, with network-disabled defaults preserved. A PubMed/LitVar adapter should retrieve metadata only, attach source provenance, cache raw payload references, and emit the same candidate-only schema. Any move from candidate evidence to applied ACMG evidence must happen outside the agent through qualified manual review and must not be implemented by relaxing these safety gates.
