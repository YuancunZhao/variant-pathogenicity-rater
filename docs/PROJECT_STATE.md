# Project State

This document is the project controller entry point for Variant Pathogenicity
Rater. It records the current software posture, implemented capabilities,
architectural safety boundaries, known limitations, and release-test baseline so
future Codex work starts from the same map instead of redesigning the system.

For the current applied evidence generation status review, see
`docs/APPLIED_EVIDENCE_STATUS.md`.

## Current Version State

The current working expectation is that day-to-day project work occurs from the
active development branch unless a release-specific branch is explicitly named.
At the time this controller document was created, the local branch was
`develop`. Prior release-readiness documentation also records historical
v0.2.0 alpha/beta review paths, but the v0.3.0 readiness record is now the
current release baseline. Future tasks should therefore confirm the current
branch before editing and preserve the documented v0.3.0 safety posture.

The project is in a v0.3.0 internal release state. The v0.3.0 readiness review
concluded that the current implementation is suitable for controlled internal
workflow testing, schema review, report review, conservative regression checks,
CLI/MCP smoke testing, provider validation review, benchmark regression, and
safety-boundary validation. This is not a clinical validation statement and
does not authorize autonomous clinical interpretation.

After VCEP signal/override framework validation, real provider validation,
benchmark Phase C, the General Literature Search and Summary Engine, the
74 real provider pipeline, the 76 mock/fixture interface audit activation,
the 77A output schema unification, the 77B provider interface consolidation,
the 77C evidence status helper unification, the 77D RuntimeOptions
foundation, the 78A real-world smoke validation layer, the 78B HGVS
resolution provider upgrade, the 78C real-world provider benchmark, and the
78D/78E/78F provider hardening passes, the
project state is: the generic SNV/small-indel interpretation loop is connected
end to end for controlled internal review, including generated applied
evidence, candidate/suggested evidence, literature search summaries,
reviewed-evidence drafts, curator-applied reviewed evidence, ClinVar review
notes, ClinGen ERepo review notes, local VCEP gene-level profile signals,
approved limited profile overrides, reports, CLI/MCP surfaces, batch and
annotated-batch VCEP summaries, local ClinVar/gnomAD/MANE/ERepo provider
validation, a 100-case offline curated fixture-backed benchmark,
natural-language input wrappers, offline variant resolution, opt-in online
ClinVar/gnomAD/Ensembl VEP/PubMed/LitVar provider adapters, shared provider
cache/provenance handling, provider outcome summaries, structured-coordinate
resolution fallback, descriptive VEP-to-resolution bridging, CLI opt-in flags,
MCP online options, canonical additive output sections for Python/CLI/MCP
single, text, batch, and annotated-batch outputs, a normalized additive
provider runtime result contract, a shared read-only evidence status view,
centralized runtime-option normalization for Python API, CLI, MCP,
natural-language text, batch, and annotated-batch entry points,
HGVS-to-protein/coordinate resolution-provider contract output,
provider benchmark metrics for ClinVar/gnomAD/VEP/PubMed/LitVar,
gnomAD GraphQL failure/no-record separation, VEP GET/POST/HGVS fallback
diagnostics, PubMed expanded query/citation fallback behavior, gnomAD
full/frequency/minimal GraphQL fallback for schema drift, provider benchmark
latency-scope/error diagnostics, Ensembl VEP POST-first/alt-only GET/HGVS
fallback stabilization, VEP timeout/error diagnostics, VEP minimal consequence
fallback, descriptive protein-change bridge from VEP transcript consequences,
Chinese laboratory reporting, and the unchanged ACMG classification combiner.
The 74 real provider pipeline has passed offline integration review with the
default no-network safety boundary intact, and the 78A real-world smoke suite
now checks six real HGVS c. inputs for structured end-to-end returns without
asserting clinical truth. The 78B resolution upgrade improves offline
descriptive resolution for the real-world smoke dataset without changing
classification or evidence generation. The 78C provider benchmark adds
provider-yield, runtime, cache, timeout, and failure observability for the same
six cases without changing `rate_variant` output or classification. The 78D
provider hardening pass improves online provider failure degradation and
benchmark diagnostics, and the 78E gnomAD fix handles legacy
`populations`/`faf95` schema drift through staged GraphQL fallback and bounded
HTTP/GraphQL diagnostics. The 78F VEP provider stabilization improves live VEP
request representation, fallback, timeout diagnostics, and descriptive
protein/consequence resolution bridging without changing classification,
applied evidence, or default no-network behavior. The next project
constraint is no longer basic workflow connectivity, rule-profile plumbing,
real provider safety posture, first-pass benchmark breadth, localization,
natural-language/HGVS text intake, HGVS c. resolution for key fixture-backed
cases, general literature search/summarization, first-pass real-world HGVS
smoke coverage, first-pass HGVS resolution provider output, or first-pass
provider hardening after 78C; it is deeper selected real-world case validation,
a narrow real VCEP profile pilot, provider
cache/reproducibility hardening, and CNV/SV framework planning.

The software positioning is deliberately conservative: Variant Pathogenicity
Rater is a semi-automated ACMG interpretation assistant for SNV/small-indel
workflows. It provides normalized variant context, auditable evidence,
criterion assessments, candidate/review-note evidence, manual reviewed evidence
intake, reports, and human-review-required classification proposals. It is not
a clinical sign-out system, not a substitute for qualified genetics review, and
not a general genome interpretation platform.

The current complete interpretation workflow is:

```text
variant input
  -> optional natural-language parsing
  -> normalization / variant resolution / annotation / context consistency
  -> automatic applied evidence generation
  -> candidate/suggested evidence
  -> manual reviewed evidence
  -> combiner
  -> report
```

## Current Capabilities

### Single Variant Workflow

The single variant workflow accepts supported HGVS-like or VCF-like SNV and
small-indel inputs, normalizes them into an internal representation, enriches
supported HGVS c. inputs through the offline fixture-backed variant resolution
layer where available, gathers mock/local evidence, applies conservative
evidence-generation layers where implemented, runs the existing ACMG
classification combiner, and returns a structured result with review flags,
provenance, limitations, and report-ready sections.

Single variant outputs remain machine proposals. They preserve human-review
requirements and separate applied ACMG evidence from candidate/review-note
evidence.

The 77A canonical output view is additive. New clients should prefer
`input`, `variant`, `context`, `runtime`, `providers`, `evidence`,
`classification`, `review`, `report`, `provenance`, `warnings`, and
`compatibility`; legacy fields such as `normalized_variant`,
`provider_mode_summary`, `applied_evidence`, `review_note_evidence`,
`final_classification`, `report_text`, and `step_results` remain emitted.
77B adds `step_results.provider_runtime` as the normalized provider runtime
contract backing provider summaries while preserving raw provider step payloads.
77C adds a shared read-only evidence status helper used for applied,
candidate-only, review-note, and reviewed evidence grouping without changing
evidence generation, reviewed-evidence validation, or the combiner.
77D adds a centralized RuntimeOptions layer for Python API, CLI, MCP,
natural-language text, batch, and annotated-batch option handling, preserving
legacy options, default mock/offline behavior, online-provider mapping
semantics, reviewed-evidence precedence, and reviewed-evidence safety
boundaries.
78A adds `data/real_world_smoke_variants_v1.json` and an offline pytest smoke
suite for six real HGVS inputs. This layer verifies structured canonical and
legacy outputs, provider/runtime/evidence auditability, limitations for
unresolved normalization/resolution state, and one natural-language text smoke
case. It does not define expected classifications and does not assess clinical
truth.

### Natural Language Input

Natural-language and mixed HGVS text input is implemented as a wrapper around
the same rating workflow. `parse_variant_text`, `rate_variant_from_text`, and
CLI `vpr rate-text` extract explicit variant/context fields, preserve missing
fields and ambiguity warnings, and can return parser-only or parse-and-rate
results. The parser does not generate ACMG evidence, does not change
classification logic, and does not bypass the combiner.

### Batch Workflow

The batch workflow supports JSON, JSONL, CSV/TSV, and VCF-like records. It keeps
row-level success and failure information, preserves malformed or unsupported
records in `failed_records`, and provides summaries without hiding per-record
limitations. Batch behavior is part of the safety surface: future evidence
features must remain batch-compatible and must not silently skip failures.
Successful records now include a `canonical_summary` subset for clients that
need stable per-record state without parsing legacy pipeline internals.

### Annotated-Batch Workflow

The annotated-batch workflow ingests common annotation-style exports including
VEP, ANNOVAR, bcftools csq, and generic annotation records. Annotation adapters
convert source rows into normalized rating inputs and retain source provenance,
quality warnings, transcript-selection context, and limitations. Annotation and
transcript-selection context are review context only; they do not generate ACMG
evidence by themselves.

### CLI

The CLI exposes the main offline workflows through commands such as single
variant rating, batch rating, annotated-batch rating, and environment checks.
CLI behavior must remain consistent with Python and MCP behavior: candidate
evidence stays separate, failures become limitations or structured errors, and
all classification outputs require review.

### MCP

The MCP server is the stable integration boundary for Codex and other tool
clients. It exposes single, batch, annotated-batch, normalization, provider,
evidence, PVS1, report, and health-oriented tools with structured schemas.
Future features that produce evidence or reports should preserve MCP
compatibility and must not bypass the same safety gates used by the Python and
CLI paths.

### Reporting

Reports render the supplied structured result. They do not recalculate ACMG
criteria, change evidence strength, or alter final classification. Reports are
responsible for making the applied/candidate split visible, surfacing
provenance and limitations, warning that VUS means uncertainty, and preserving
human-review-required language.

Reports include a Variant Resolution Summary when available. This section shows
descriptive transcript, protein consequence, coordinate, exon, NMD, confidence,
and limitation context. It is not ACMG evidence and is not counted by the
classification combiner.

### Literature Workflow

The literature workflow is a review-note and suggestion workflow. It may
surface claims relevant to PS3/BS3, PS2/PM6, PP1, PS4, PM3, PP4, PS1/PM5,
PM1, and PVS1 mechanism support, but those outputs remain candidate-only unless
the manual reviewed evidence workflow explicitly supplies a valid
`reviewed_applied` record under strict gates. Literature retrieval, extraction,
query planning, duplicate collapse, criterion summaries, and confidence scoring
do not by themselves authorize applied evidence.

The General Literature Search and Summary Engine is implemented and has passed
integration review. `search_and_summarize_literature` supports deterministic
query planning, local/offline caller-supplied literature records, duplicate
publication/family/cohort collapse, criterion-specific summaries, blocking
flags for variant or disease mismatch, limitations for abstract-only evidence,
review flags for low-confidence extraction, and reviewed-evidence draft
generation. Codex/Life Science Research literature records are treated as
caller-supplied records, not trusted clinical evidence.

Literature suggestions can be converted into reviewed-evidence drafts. Drafts
default to non-applied review status and require curator editing before they can
be submitted as `reviewed_applied`. `suggested_strength` is reviewer guidance
only; literature-derived evidence-like outputs use candidate/review-note
semantics and do not change classification.

### External Curated Source Integration

External curated-source integration is implemented for ClinVar and ClinGen
Evidence Repository.

ClinVar supports review-note output and conservative comparator-based PS1/PM5
generation. ClinVar assertions are not copied into classification as PP5/BP6
and do not override user-supplied context.

ClinGen ERepo supports gene-level VCEP activity signals, exact variant match
review notes, supporting summaries, citations, provenance, and
reviewed-evidence draft generation. ERepo exact variant matches are review
notes, not automatic applied evidence. ERepo supporting summaries can seed
reviewed-evidence drafts, but those drafts must pass through the same manual
review workflow before any criterion can be counted.

No external curated source automatically classifies a variant. ClinVar, ERepo,
and literature outputs remain candidate/review-note material unless a curator
explicitly supplies valid `reviewed_applied` evidence with provenance and audit
trail.

### Real Provider Validation

Real provider validation is complete for the current provider surface:

- ClinVar real provider validation.
- gnomAD local snapshot validation.
- ClinVar online provider adapter validation with mocked HTTP.
- gnomAD online GraphQL adapter validation with mocked HTTP.
- Ensembl VEP online REST adapter validation with mocked HTTP.
- PubMed/LitVar online literature surface validation with mocked HTTP.
- MANE transcript validation.
- Real resolution provider snapshot validation.
- ClinGen ERepo validation.

ClinVar uses local fixture/local-file validation and optional online behavior
that remains disabled by default. It provides review notes and comparator facts
for PS1/PM5, but ClinVar assertions do not directly apply PP5/BP6 or classify
a variant.

gnomAD validation uses local snapshots that map into the population-frequency
schema. Population providers supply AF/AC/AN/FAF, ancestry, quality, build, and
source-version facts only. `population_rules` remains the only path to applied
`BA1`, `BS1`, or `PM2_Supporting`, and a provider miss is limitation-only.

MANE/RefSeq/Ensembl transcript validation uses local annotation fixtures.
Transcript metadata supports transcript review, exon/NMD context, and PVS1
review assumptions, but it cannot apply PVS1, PP3, BP4, or any other
criterion by itself.

Variant resolution is implemented as a separate offline descriptive layer after
normalization. Local transcript-resolution fixtures can enrich HGVS c. inputs
with transcript, protein, coordinate, exon, and NMD facts, preserving both the
original `normalized_variant` and the enriched `resolved_variant`. Resolution
does not generate `EvidenceItem` records and does not directly change
classification.

Real resolution provider validation now covers local snapshot-backed transcript,
protein consequence, coordinate, exon, and NMD resolution for BRCA1, CFTR,
GJB2, DMD, PAH, and TP53, plus missing-mapping behavior for BRCA2. Build,
transcript accession, and transcript-version mismatches are review flags, while
malformed or missing provider mappings remain limitations only.

ClinGen ERepo validation covers exact variant review notes, gene-level VCEP
activity signals, supporting summaries, citations, provenance, cache behavior,
and reviewed-evidence drafts. Exact matches and supporting summaries remain
review-note or draft material unless a curator submits valid
`reviewed_applied` evidence.

Across all validated providers, local fixtures or local snapshots are the
primary validation path, optional online behavior is explicitly gated and
disabled by default, cache/provenance/limitations are visible, failures degrade
to structured limitations, and no provider directly changes classification.
ClinVar online records do not trigger PP5/BP6, PubMed/LitVar records remain
candidate-only literature inputs, gnomAD and VEP online facts flow only through
the existing population and computational evaluators, no gnomAD record triggers
PM2 by itself, and candidate evidence remains outside the combiner.

Provider mode reporting is now explicit. `mock_mode` remains for backward
compatibility, and `data_source_modes` reports configured/requested modes after
runtime options are applied. Actual provider outcomes are reported in
`provider_mode_summary`, including requested mode, configured mode, outcome,
source version, endpoint, query, raw hash, cache hit, provider mode, record
count, and limitations. `offline_default_mode` and
`unresolved_placeholder_mode` make default-off and unresolved placeholder
states visible.

The 77A canonical output view maps these legacy provider/runtime fields into
`runtime` and `providers.summary` without changing provider behavior or default
network policy. Raw `step_results` remain a compatibility/debug payload and
have not been migrated. 77B adds `step_results.provider_runtime` as a
normalized provider outcome/provenance contract while preserving the original
provider step payloads.

### Benchmark Validation

Benchmark Phase C is complete and is the current validation baseline.

Current benchmark status:

- 100 offline curated SNV/small-indel cases.
- Benchmark version `offline-curated-v4-phase-c`.
- Provider fixture-backed through `data/benchmark_provider_fixtures/`.
- Includes local population, ClinVar, computational, literature, ClinGen
  ERepo, VCEP profile, annotation, and transcript metadata fixtures.
- Latest full regression status after 74 real provider pipeline integration
  review: `655 passed, 2 skipped`.

The benchmark covers generated and reviewed evidence boundaries for `PVS1`,
`BA1`, `BS1`, `PM2_Supporting`, `PP3`, `BP4`, `PS1`, `PM5`, manual reviewed
evidence, literature draft workflows, ClinGen ERepo review-note behavior, VCEP
signal/override behavior, provider limitations, transcript/MANE validation,
and candidate/applied evidence separation. It remains a safety-oriented
regression set, not a clinical truth set.

### VCEP Signal / Override Framework

The VCEP signal/override framework is implemented and validated as a
lightweight local rule-profile layer. It supports gene-level VCEP profile
signals, approved profile overrides, draft/provisional signal-only profiles,
deprecated limitation-only profiles, profile conflict blocking, and per-record
`vcep_profile_summary` output for both batch and annotated-batch workflows.

VCEP behavior is explicitly opt-in. Signals alone cannot change classification.
Approved overrides are limited to safe generator parameters or post-generator
downgrades and cannot bypass generator safety gates, create evidence, promote
candidate evidence, or modify the combiner. Disabled criteria are converted to
candidate/review-note material with review flags and provenance rather than
being silently deleted.

Override provenance and report visibility are required. Affected evidence items
carry `supporting_data.vcep_override`, structured results expose
`vcep_profile_context` / `vcep_profile_summary`, and reports include a separate
VCEP Signal / Rule Profile section outside Applied ACMG Evidence.

### Manual Reviewed Evidence Workflow

Manual reviewed evidence is implemented as the explicit curator bridge from
candidate/suggested evidence or independent curated knowledge into applied ACMG
evidence. Only records with `evidence_status=reviewed_applied`, valid strength
and direction, curator decision, rationale, review date, and citation or
provenance are converted into applied `EvidenceItem` records. `reviewed_rejected`
and `needs_more_info` records remain review notes.

This workflow supports curator-reviewed application of high-risk criteria such
as `PS3`, `BS3`, `PS2`, `PM6`, `PP1`, `PS4`, `PP4`, and `PM3` when the reviewer
explicitly supplies the reviewed record. Candidate evidence is never changed in
place and `source_candidate_evidence_id` is only a trace link.

## Applied Evidence Currently Implemented

The current applied evidence generation surface includes:

- `PVS1`
- `BA1`
- `BS1`
- `PM2_Supporting`
- `PP3`
- `BP4`
- `PS1`
- `PM5`

These are generated before the classification combiner runs. In addition,
curator-reviewed `reviewed_applied` records can supply applied ACMG evidence,
including reviewed `PS3`, `BS3`, `PS2`, `PM6`, `PP1`, `PS4`, `PP4`, and `PM3`.
Manual reviewed evidence is not automatic evidence generation; it is an
explicit curator action with provenance and audit trail requirements.

Generated and reviewed applied evidence are supplied upstream of the
classification combiner. The combiner
remains isolated: it combines only the evidence it receives and should not be
modified merely to support a new evidence generator. Applied generated evidence
requires review, must include provenance, and must preserve limitations when
context is missing, conflicting, or too weak.

PVS1 is implemented for conservative SNV/small-indel loss-of-function contexts.
Population evidence is constrained by disease-specific thresholds, source
quality, ancestry/population context, genome build, allele number and coverage,
and context consistency. Computational PP3/BP4 is consensus-based,
supporting-only, and blocked by conflicts or inappropriate variant contexts.
ClinVar-derived PS1/PM5 is implemented as a conservative comparator workflow
that requires high-quality non-conflicting germline P/LP comparators, protein
and nucleotide distinction, transcript/protein match, disease/condition match,
and context consistency. ClinVar assertions do not become PP5/BP6 evidence.

## Candidate / Review-Note Evidence Currently Implemented

The current candidate/review-note surface includes:

- ClinVar review notes.
- ClinGen Evidence Repository review notes, VCEP activity signals, and
  reviewed-evidence drafts.
- Literature evidence agent output.
- `PS3` / `BS3` suggestions.
- `PS2` / `PM6` suggestions.
- `PP1` / `PS4` / `PP4` suggestions.
- `PM3` suggestions.
- `PS1` / `PM5` candidate-only fallbacks when comparator, context, condition,
  transcript/protein, nucleotide-distinction, or ClinVar quality gates are
  insufficient for applied evidence.

These items are intentionally outside the classification combiner. They may
guide human review, report questions, benchmark expectations, or future
workflow design, but they must not count as applied ACMG evidence unless the
manual reviewed evidence workflow explicitly supplies a valid
`reviewed_applied` record under documented release gates.

## Safety Architecture

### Candidate-Only Separation

Candidate and review-note evidence is structurally separate from applied ACMG
evidence. Candidate-only items must remain visible for review but excluded from
classification. This separation is a core safety boundary, not a presentation
preference. There must be no silent candidate conversion: candidate, suggested,
or review-note evidence can enter the combiner only through explicit curator
review and a valid `reviewed_applied` record.

### Combiner Isolation

The ACMG classification combiner is a protected component. It should not be
changed to accommodate provider behavior, literature extraction, report
wording, or roadmap experiments. Future evidence work should produce valid
`EvidenceItem` and criterion data upstream, with tests proving candidate-only,
neutral, conflicting, and `strength: none` evidence remains uncounted.

### Review Requirement

All generated applied evidence and all classification results require human
review. Reviewed evidence also requires explicit curator action and retained
review provenance. The system may propose, organize, and explain; it must not
sign out. Report, CLI, MCP, batch, and annotated-batch outputs must keep
review-required language intact.

### Provenance

Every provider-derived or generated evidence item must retain source,
retrieval/query context, source version or snapshot identity when available,
timestamp or run context, and limitations. Provenance is required for
auditability and for later distinguishing local/mock, offline, and opt-in
online observations.

### Context Consistency

Context consistency checks flag gene, transcript, disease, inheritance,
ancestry, consequence, provider-record, and genome-build mismatches. These
checks protect evidence generation from mismatched assumptions. They do not
generate ACMG evidence and do not change the combiner.

### Transcript Selection

Transcript selection provides review context and prioritization. It does not
override explicitly supplied user context, does not itself generate evidence,
and must not be treated as proof that provider or literature evidence matches
the rating context.

### Noisy Input Hardening

The system hardens common real-world input problems including BOMs, comments,
alias columns, mixed-case columns, `chr` prefixes, lowercase alleles,
URL/HTML-escaped HGVS values, ambiguous alleles, multiallelic-looking records,
symbolic ALT values, and CNV/SV-like inputs. Unsafe input should be rejected,
warned, or preserved with structured limitations rather than silently
interpreted.

### Online Provider Gating

The default provider posture is offline/local/mock. Real provider validation is
based primarily on local fixtures or local snapshots. Optional online ClinVar
and ClinGen ERepo behavior is opt-in only and disabled by default. Online
population, transcript, literature, and computational providers are not default
runtime dependencies for the current beta. Any future online provider must
default off, require explicit enablement, preserve provenance/cache metadata,
and degrade to limitations on failure.

### Failure-To-Limitation

Missing provider data, provider failure, parser uncertainty, context conflicts,
network failure, and unsupported scope must become structured limitations,
warnings, or failed records. They must not become inferred absence, hidden
success, or upgraded confidence.

## Current Unsupported Scope / Limitations

The current project does not support:

- CNV interpretation.
- SV interpretation.
- Repeat disorders or repeat expansion interpretation.
- Mitochondrial variant interpretation.
- Methylation evidence.
- DMD complex SV handling.
- Clinical sign-out or autonomous clinical reporting.
- Automatic literature-applied evidence.
- Trio/family-aware automation.
- Full disease-specific VCEP reasoning engines.
- Automatic default activation of VCEP profiles.
- Automatic `PS3`/`BS3`, `PS2`/`PM6`, `PP1`, `PS4`, `PP4`, or `PM3`
  application unless explicitly supplied through manual reviewed evidence.
- Automatic evidence application from ClinVar, ClinGen ERepo, or literature
  unless explicitly supplied through manual reviewed evidence.

Additional excluded or limited areas include RNA-seq evidence, long-read
phasing evidence, exon-level deletion interpretation, complex rearrangements,
external liftover or transcript-mapping services, and automatic provider
override of user-supplied context.

## Current Test Status

The latest documented full regression run after 74 real provider pipeline
integration review recorded:

- Full pytest: `655 passed, 2 skipped`.
- Benchmark coverage: 100 curated offline SNV/small-indel cases.
- Benchmark version: `offline-curated-v4-phase-c`.
- Benchmark provider posture: fixture-backed, including annotation and
  transcript metadata fixtures, with online provider tests mocked and live
  smoke tests env-gated.

The benchmark is safety-oriented rather than a clinical truth set. It checks
classification behavior, applied/candidate evidence separation, conservative
VUS defaults, population-threshold context, ClinVar conflict handling, PVS1
restraint, reviewed evidence, literature drafts, ERepo review-note behavior,
VCEP signal/override boundaries, provider limitations, provenance, and
transcript/MANE validation. The smoke suite exercises representative
real-variant examples offline and checks that ClinVar/literature candidate
evidence does not leak into applied classification.

Future release reviews should refresh these counts from the current branch
instead of assuming they are still exact.

## Current Roadmap Priority

The recommended next task is selected real-world case validation, followed by
one narrowly scoped real VCEP profile pilot behind explicit profile selection.

Real provider validation for ClinVar, gnomAD, Ensembl VEP, PubMed/LitVar,
MANE, and ERepo is complete for the current provider surface and should now be
maintained as a regression boundary: local fixture/snapshot validation,
optional online disabled by default, provenance/cache visibility,
failure-to-limitation behavior, and no direct provider-driven classification.

Current known gaps are selected real-world case validation, a selected real
VCEP profile pilot, larger real-world hospital annotation validation, broader
resolution fixture coverage
beyond the initial targeted records, provider cache/reproducibility hardening,
and CNV/SV support.
