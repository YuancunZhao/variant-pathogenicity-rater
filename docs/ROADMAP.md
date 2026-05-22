# Roadmap

## MVP Goal

Build a Python 3.11+ Codex Plugin and MCP server for single-site SNV/small indel
ACMG pathogenicity rating.

The MVP should produce:

- Normalized variant representation
- Auditable evidence chain
- ACMG criterion assessments
- Five-tier classification proposal
- Human review required notice
- JSON and Markdown reports

## Non-Goals For Phase 1

Do not implement:

- CNV interpretation
- SV interpretation
- DMD complex SV handling
- Repeat expansion interpretation
- Mitochondrial variant interpretation
- Methylation evidence
- RNA-seq evidence
- Long-read evidence

## Milestone 1: Project Skeleton

Deliverables:

- Python 3.11+ package layout
- MCP server entry point
- Codex plugin metadata
- Pydantic v2 dependency
- pytest setup
- Initial docs

Acceptance criteria:

- MCP server starts locally
- Tool listing works
- Test runner works
- Documentation states SNV/small indel-only scope

## Milestone 2: Core Schemas

Deliverables:

- VariantInput schema
- NormalizedVariant schema
- EvidenceItem schema
- CriterionAssessment schema
- ClassificationResult schema
- VariantReport schema
- Provenance and audit schemas

Acceptance criteria:

- Schemas validate representative HGVS and VCF-like inputs
- Schemas reject unsupported variant classes
- Evidence items require provenance
- Classification values are restricted to the five ACMG categories

## Milestone 3: Variant Normalization Framework

Deliverables:

- HGVS input parser interface
- VCF-like input parser interface
- SNV/small indel scope validator
- Normalization warning model
- `normalize_variant` MCP tool

Acceptance criteria:

- HGVS input produces a NormalizedVariant object
- VCF-like input produces a NormalizedVariant object
- CNV/SV-like inputs are rejected with structured errors
- All normalization responses include audit-friendly warnings or notes

## Milestone 4: Evidence Retrieval Frameworks

Deliverables:

- ClinVar evidence framework
- Population frequency evidence framework
- Computational evidence framework
- Literature evidence framework
- Source provenance and raw snapshot metadata model

Acceptance criteria:

- Each framework returns standard EvidenceItem objects
- EvidenceItem objects include source, query, retrieval time, and provenance
- Retrieval modules do not directly return final ACMG classifications

## Milestone 5: ACMG Criteria Evaluators

Deliverables:

- BA1 evaluator
- BS1 evaluator
- PM2 evaluator
- PP3 evaluator
- BP4 evaluator
- PVS1 evaluator for SNV/small indel LoF variants

Acceptance criteria:

- Each evaluator returns CriterionAssessment objects
- Each assessment links to one or more EvidenceItem IDs when evidence is used
- PVS1 is limited to SNV/small indel LoF logic in phase 1
- Unsupported evidence types are marked unavailable rather than inferred

## Milestone 6: Classification Combiner

Deliverables:

- ACMG combination logic
- Conflict handling
- VUS fallback
- Human review required flag

Acceptance criteria:

- Combiner returns only Pathogenic, Likely pathogenic, VUS, Likely benign, or
  Benign
- Conflicting pathogenic and benign evidence is surfaced
- Human review is always required
- Combiner has golden tests for all five categories

## Milestone 7: MCP Tool Surface

Deliverables:

- `rate_variant`
- `normalize_variant`
- `query_clinvar`
- `query_population_frequency`
- `evaluate_pvs1`
- `evaluate_computational_evidence`
- `search_literature_evidence`
- `generate_report`

Acceptance criteria:

- Tools expose JSON schemas
- Tools return structured errors
- `rate_variant` orchestrates the MVP workflow
- Integration tests cover tool calls

## Milestone 8: Report Generation

Deliverables:

- JSON evidence chain report
- Markdown report
- Human review checklist
- Audit summary section

Acceptance criteria:

- Report includes normalized variant
- Report includes all evidence items
- Report includes criterion assessments
- Report includes classification proposal
- Report clearly states human review is required

## Milestone 9: Hardening

Deliverables:

- Contract tests
- Golden tests
- Audit completeness tests
- Error-path tests
- Developer documentation

Acceptance criteria:

- Tests cover happy paths and rejected out-of-scope inputs
- Every criterion assessment can be traced to evidence or an explicit absence of
  evidence
- Every evidence item has provenance
- README documents setup, scope, tools, and test commands

## Future Extension Track

Future work may add CNV/SV support by introducing new modules, schemas, and rule
profiles. These future capabilities must not be implemented in phase 1.

Potential future modules:

- CNV interval normalization
- SV breakpoint normalization
- Dosage sensitivity evidence
- DMD-specific complex SV profile
- Repeat expansion profiles
- RNA evidence providers
- Long-read phasing evidence
- Methylation evidence

