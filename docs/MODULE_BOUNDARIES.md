# Module Boundaries

## Boundary Principles

The first phase is a modular SNV/small indel ACMG rater. Each module owns one
kind of responsibility and communicates through Pydantic v2 schemas.

Important rules:

- MCP tools orchestrate modules but do not contain ACMG business logic.
- Evidence modules retrieve and normalize evidence but do not make final
  classification decisions.
- ACMG modules evaluate criteria but do not fetch external data.
- The classification combiner combines criteria but does not retrieve evidence.
- Reports render structured data but do not recalculate criteria.
- All modules must preserve auditability.

## Proposed Package Layout

```text
src/
  variant_pathogenicity_rater/
    mcp/
      server.py
      tools.py
    schemas/
      common.py
      variant.py
      evidence.py
      acmg.py
      classification.py
      report.py
    normalization/
      normalizer.py
      hgvs_parser.py
      vcf_parser.py
      transcript_mapping.py
    evidence/
      clinvar.py
      population.py
      computational.py
      literature.py
      provenance.py
    acmg/
      population_rules.py
      computational_rules.py
      pvs1.py
      combiner.py
      profiles.py
    reporting/
      generator.py
      markdown.py
      json_report.py
    audit/
      event_log.py
      source_snapshot.py
    config/
      settings.py
      thresholds.py
```

The current repository may keep an existing `mcp-server/` directory during early
scaffolding. The long-term package boundary should still follow the structure
above or an equivalent layout with the same responsibilities.

## MCP Layer

Owns:

- MCP server startup
- Tool registration
- Tool input validation
- Workflow orchestration
- Tool response serialization
- Structured errors

Does not own:

- Variant parsing details
- Evidence retrieval details
- ACMG criteria details
- Classification rules
- Report rendering details

Primary dependencies:

- Schemas
- Normalization service
- Evidence services
- ACMG services
- Report generator

## Schemas

Owns:

- Pydantic v2 data contracts
- Enums for variant type, evidence type, criterion, strength, status, and
  classification
- Field-level validation
- Serialization contracts

Does not own:

- External API calls
- ACMG interpretation logic
- Report rendering

Required schema groups:

- VariantInput
- NormalizedVariant
- EvidenceItem
- EvidenceSource
- EvidenceProvenance
- CriterionAssessment
- EvidenceChain
- ClassificationResult
- HumanReviewBlock
- VariantReport

## Normalization

Owns:

- HGVS input parsing
- VCF-like input parsing
- Genome build handling
- SNV/small indel detection
- Canonical internal variant representation
- Normalization warnings

Does not own:

- Population frequency lookup
- ClinVar lookup
- ACMG criteria evaluation
- Final classification

Hard boundary:

- CNV, SV, repeat expansion, mitochondrial, long-read, RNA, and methylation
  interpretation must be rejected or marked unsupported in phase 1.

## Evidence

Owns:

- Querying or adapting evidence sources
- Mapping source-specific data into EvidenceItem objects
- Recording source metadata
- Recording query provenance
- Recording raw snapshot references when available

Does not own:

- ACMG criterion application
- Classification combining
- Human review decisions

Evidence providers in phase 1:

- ClinVar framework
- Population frequency framework
- Computational prediction framework
- Literature evidence framework

## ACMG Evaluators

Owns:

- Translating EvidenceItem objects into CriterionAssessment objects
- Applying configured thresholds
- Assigning criterion status and strength
- Producing rationale text linked to evidence IDs

Phase 1 evaluator modules:

- `population_rules.py`: BA1, BS1, PM2
- `computational_rules.py`: PP3, BP4
- `pvs1.py`: PVS1 for SNV/small indel LoF variants only

Does not own:

- Fetching evidence
- Final five-tier classification
- Report rendering

## Classification Combiner

Owns:

- Combining CriterionAssessment objects under ACMG combination logic
- Returning the five-tier machine classification proposal
- Detecting conflicts
- Falling back to VUS when evidence is insufficient
- Marking human review as required

Does not own:

- Evidence retrieval
- Criterion-level evidence evaluation
- Final human sign-out

## Reporting

Owns:

- JSON report generation
- Markdown report generation
- Evidence chain presentation
- Human review checklist presentation
- Audit summary presentation

Does not own:

- Re-running evidence queries
- Recalculating criteria
- Changing classification

## Audit

Owns:

- Event log abstractions
- Source snapshot references
- Checksums
- Retrieval timestamps
- Provenance completeness checks

Does not own:

- Clinical interpretation
- External source-specific parsing

## Configuration

Owns:

- Runtime settings
- Threshold configuration
- Source toggles
- Profile names and versions

Does not own:

- Hard-coded evidence decisions
- User-facing report content

## Extension Boundary

Future CNV/SV support should add new modules instead of expanding phase 1
modules beyond their scope.

Examples:

- `normalization/cnv_normalizer.py`
- `normalization/sv_normalizer.py`
- `evidence/dosage.py`
- `acmg/cnv_rules.py`
- `acmg/sv_rules.py`

These modules are intentionally out of scope for the first phase.

