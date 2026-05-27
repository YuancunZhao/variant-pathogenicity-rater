# gnomAD Local Snapshot Validation

This document defines the offline validation path for gnomAD-like local
population snapshots used by BA1, BS1, and PM2_Supporting evidence generation.
It validates provider parsing, provenance, cache behavior, safety downgrades,
and report visibility. It does not change the ACMG classification combiner.

## Fixture Format

The validation fixture lives at
`data/fixtures/gnomad_local_snapshot_validation.jsonl`. Each usable JSONL row is
a single normalized population observation with these fields:

- `chromosome`, `position`, `ref`, `alt`
- `genome_build`
- `overall_af`, `max_pop_af`, `faf95`, `filtering_af`
- `allele_count`, `allele_number`, `homozygote_count`, `hemizygote_count`
- `population_name`, `coverage_quality`, `population_match`
- `source_version`

The provider maps `source_version` into the existing `PopulationFrequency`
schema through `source.version`, `data_version`, `dataset_version`, and
provenance metadata. The provider should not introduce a new public population
schema field just to support this fixture.

## Validation Scenarios

The local snapshot validation covers:

- No record found: returns no usable AF and a limitation; this is not evidence
  of absence and cannot trigger PM2_Supporting.
- Zero AF with high AN: may support PM2_Supporting only after disease context,
  configured disease-specific thresholds, source version, coverage, population
  match, and genome build gates pass.
- Zero AF with low AN: PM2_Supporting remains candidate-only.
- High AF BA1 and BS1: applied only with configured disease-specific thresholds
  and complete disease, inheritance, prevalence, penetrance, population, source,
  coverage, and build context.
- Ancestry mismatch, low coverage, founder population warning, missing source
  version, or genome-build mismatch: candidate-only or limitation-only.
- Provider failure, malformed rows, symbolic alleles, and multiallelic alleles:
  limitations only; no pipeline crash and no inferred PM2.

## Provider And Provenance Behavior

Local-file population lookup remains offline by default. Network access is not
required for validation and must not be introduced into default tests.

Every returned `PopulationFrequency`, including misses and provider failures,
must preserve an `EvidenceSource` with provenance where available:

- provider name and source version
- query fields
- retrieval timestamp
- raw-record hash or miss/failure hash
- parser version
- population, allele number, coverage quality
- limitations

The disk cache key includes provider, mode, source version, and query. Tests
should use temporary cache directories and explicit source versions so fixture
changes do not leak across scenarios.

## Evidence Safety

The population provider supplies normalized facts only. BA1, BS1, and
PM2_Supporting decisions remain in the population evidence generator and
`acmg.population_rules`; the classification combiner remains unchanged.

Applied evidence remains review-required. Candidate-only population evidence
must use `strength=none`, `candidate_only=true`, and `applied=false`, and must
remain outside the combiner. Reports, CLI, MCP, batch, and annotated-batch
outputs must preserve applied versus candidate evidence separation plus the
population decision path, thresholds, quality checks, blockers, limitations,
and provenance.
