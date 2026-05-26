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
`develop`. Prior release-readiness documentation also records a
`feature/beta-gap-analysis` review path for the v0.2.0-beta internal testing
gate. Future tasks should therefore confirm the current branch before editing,
but should treat the documented beta safety posture as the controlling design
baseline.

The project is in an internal beta state. The v0.2.0-beta review concluded that
the current implementation is suitable for controlled internal workflow testing,
schema review, report review, conservative regression checks, CLI/MCP smoke
testing, and safety-boundary validation. This is not a clinical validation
statement and does not authorize autonomous clinical interpretation.

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
  -> normalization / annotation / context consistency
  -> automatic applied evidence generation
  -> candidate/suggested evidence
  -> manual reviewed evidence
  -> combiner
  -> report
```

## Current Capabilities

### Single Variant Workflow

The single variant workflow accepts supported HGVS-like or VCF-like SNV and
small-indel inputs, normalizes them into an internal representation, gathers
mock/local evidence, applies conservative evidence-generation layers where
implemented, runs the existing ACMG classification combiner, and returns a
structured result with review flags, provenance, limitations, and report-ready
sections.

Single variant outputs remain machine proposals. They preserve human-review
requirements and separate applied ACMG evidence from candidate/review-note
evidence.

### Batch Workflow

The batch workflow supports JSON, JSONL, CSV/TSV, and VCF-like records. It keeps
row-level success and failure information, preserves malformed or unsupported
records in `failed_records`, and provides summaries without hiding per-record
limitations. Batch behavior is part of the safety surface: future evidence
features must remain batch-compatible and must not silently skip failures.

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

### Literature Workflow

The literature workflow is a review-note and suggestion workflow. It may
surface claims relevant to PS3/BS3, PS2/PM6, PP1/PS4/PP4, PM3, and PS1/PM5,
but those outputs remain candidate-only unless the manual reviewed evidence
workflow explicitly supplies a valid `reviewed_applied` record under strict
gates. Literature retrieval, extraction, and confidence scoring do not by
themselves authorize applied evidence.

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

The default provider posture is offline/local/mock. Online ClinVar is opt-in
only and candidate-only. Other online population, literature, and computational
providers are not implemented for the current beta. Any future online provider
must default off, require explicit enablement, preserve provenance, and degrade
to limitations on failure.

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
- Disease-specific VCEP rule profiles.
- Automatic `PS3`/`BS3`, `PS2`/`PM6`, `PP1`, `PS4`, `PP4`, or `PM3`
  application unless explicitly supplied through manual reviewed evidence.

Additional excluded or limited areas include RNA-seq evidence, long-read
phasing evidence, exon-level deletion interpretation, complex rearrangements,
external liftover or transcript-mapping services, and automatic provider
override of user-supplied context.

## Current Test Status

The latest documented v0.2.0-beta release gate recorded:

- Approximate full pytest count: 282 passed.
- Benchmark coverage: 21 curated offline SNV/small-indel cases.
- Real-data smoke coverage: 10 curated offline cases.

The benchmark is safety-oriented rather than a clinical truth set. It checks
classification behavior, evidence separation, conservative VUS defaults,
population-threshold context, ClinVar conflict handling, and PVS1 restraint.
The smoke suite exercises representative real-variant examples offline and
checks that ClinVar/literature candidate evidence does not leak into applied
classification.

Future release reviews should refresh these counts from the current branch
instead of assuming they are still exact.
