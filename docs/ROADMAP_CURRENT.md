# Current Roadmap

This roadmap is the governance-facing roadmap for Variant Pathogenicity Rater.
It should be read with `docs/PROJECT_STATE.md`, `docs/KNOWN_LIMITATIONS.md`,
`docs/APPLIED_EVIDENCE_GENERATION.md`, and
`docs/APPLIED_EVIDENCE_STATUS.md` before planning future work.

The current roadmap priority is not to broaden the clinical surface quickly. It
is to extend reviewable evidence support while preserving the existing safety
architecture: candidate-only evidence remains outside the combiner, applied
evidence remains review-required, online behavior remains opt-in, and failures
remain limitations.

## Completed Phases

### Phase 1: PVS1

The PVS1 phase established conservative SNV/small-indel loss-of-function
evidence generation. It introduced consequence and HGVS LoF parsing, LoF
mechanism resolution, transcript relevance checks, NMD and terminal-exon
assessment, splice-specific handling, a conservative decision tree, and
conversion into applied `EvidenceItem` records.

The important architecture lesson from Phase 1 is that PVS1 is not applied from
variant consequence labels alone. Disease mechanism, transcript relevance,
NMD/splice context, limitations, and manual review remain part of the safety
contract.

### Phase 2: Population

The population phase added conservative generation for `BA1`, `BS1`, and
`PM2_Supporting`. Population decisions require disease-specific threshold
context, appropriate penetrance and ancestry assumptions, source/version
provenance, compatible genome build, adequate allele number and coverage, and
no blocking context conflict.

This phase established that a provider miss is not evidence of absence. Missing
or low-quality frequency data becomes unavailable or limitation-only; it does
not automatically trigger PM2.

### Phase 3: Computational

The computational phase added consensus-based `PP3` and `BP4` generation.
These criteria are supporting-only, review-required, blocked by predictor
conflict, and inappropriate for contexts such as frameshift/nonsense/CNV/SV
where missense-style predictors would double-count or misrepresent evidence.

This phase also formalized that SpliceAI and similar predictors provide
computational splice support only. They are not RNA validation, functional
assay evidence, `PS3`, `BS3`, or `PVS1`.

### Phase 4: ClinVar-Derived PS1/PM5

The ClinVar-derived PS1/PM5 phase added conservative comparator-based evidence
generation for `PS1` and `PM5`. It uses ClinVar P/LP records only as comparator
records and independently checks protein change, nucleotide distinction,
transcript/protein match, condition match, germline applicability, assertion
quality, conflict status, provenance, and context consistency before emitting
applied evidence.

This phase formalized that ClinVar assertions do not become PP5/BP6 evidence.
Low-quality, conflicting, somatic-only, same-variant, condition-mismatched, or
context-mismatched comparators remain candidate-only or blocked.

## Highest Priority Current Tasks

### 1. Manual Reviewed Evidence Workflow

Goal: add a controlled way for a human reviewer to supply explicitly reviewed
ACMG evidence items without confusing them with machine-suggested candidate
evidence.

Why it matters: real interpretation workflows often require human-approved
evidence from literature, segregation, functional assays, case observations, or
curated lab knowledge. The system needs a safe path for reviewed user-supplied
evidence before it can support broader validation.

Architecture impact: likely touches input schemas, validation, provenance,
reporting, batch compatibility, CLI/MCP arguments, and tests. The combiner may
receive these reviewed items as normal evidence, but the combiner logic itself
should remain unchanged.

Safety risks: the workflow must prevent candidate evidence from being silently
promoted. It must distinguish user-reviewed applied evidence from
machine-generated applied evidence and from candidate suggestions. It must
preserve audit trails and reviewer intent.

Expected deliverables: schema for reviewed evidence input, strict validation,
source/reviewer provenance, report labeling, batch support, CLI/MCP parity, and
tests covering invalid strengths, unsupported criteria, candidate promotion
attempts, and review-required preservation.

Release gate expectations: pytest pass, combiner unchanged unless explicitly
reviewed, applied/candidate separation tests, report wording safety check, and
documentation of allowed reviewer responsibilities.

### 2. Literature Suggested Evidence Review Workflow

Goal: improve the literature agent as a review workflow for PS3/BS3, PS2/PM6,
PP1/PS4/PP4, PM3, and PS1/PM5-related suggestions while keeping all
literature-derived evidence review-required and candidate-only by default.

Why it matters: literature evidence is high-value but high-risk. It requires
variant matching, disease matching, assay validity, family/trio context,
deduplication, and manual judgment.

Architecture impact: expected changes may involve literature input parsing,
suggestion schemas, provenance, report sections, and optional online-gated
retrieval. It should not affect applied evidence generation or the combiner
unless a separate reviewed evidence workflow is used.

Safety risks: computational predictions must not become functional evidence;
SpliceAI must not become RNA validation; ambiguous de novo claims must not
become PS2; unclear segregation must not become PP1; case counts must not be
double-counted across publications.

Expected deliverables: clearer suggestion records, confidence and limitation
fields, deduplication notes, review questions, report-safe wording, and tests
showing literature output remains candidate-only.

Release gate expectations: no automatic literature-applied evidence, no
combiner changes, pytest pass, candidate leakage check, report wording review,
and updated literature limitations.

### 3. VCEP Profile Framework

Goal: design and then implement an explicit profile framework for
disease/gene-specific rule settings without hard-coding VCEP behavior into
generic ACMG logic.

Why it matters: disease-specific thresholds and VCEP rules are essential for
real interpretation, but they are high-risk because generic automation can
become overconfident when context is incomplete.

Architecture impact: likely touches configuration, schemas, evidence generator
inputs, provenance, and documentation. It should be introduced behind explicit
profile selection and should not silently change default behavior.

Safety risks: accidental default VCEP profile activation, mixing profiles
between diseases, threshold misuse, and unreviewed rule overrides.

Expected deliverables: design document first, profile schema, explicit profile
selection, provenance for profile version, tests for missing/mismatched profile
context, and no default clinical profile activation.

Release gate expectations: design review before implementation, pytest pass,
benchmark cases for profile off/on behavior, limitations update, and explicit
combiner impact review.

### 4. Benchmark Expansion

Goal: expand the curated benchmark beyond the current beta-sized set while
keeping it offline, auditable, and safety-focused.

Why it matters: the current 21-case benchmark is useful but small. More cases
are needed to catch regressions in PVS1 restraint, population thresholds,
computational conflicts, ClinVar conflict handling, and candidate evidence
separation.

Architecture impact: should primarily touch data fixtures and tests, not
runtime business logic. This is a validation/hardening task rather than feature
implementation.

Safety risks: benchmark expected classifications must not be used to justify
weakening safety logic. Uncertain cases should allow conservative outcomes
rather than forcing overconfident labels.

Expected deliverables: expanded curated case file, rationale per case, expected
applied/candidate evidence, expected limitations/review flags, and updated
benchmark documentation.

Release gate expectations: benchmark pass, full pytest pass, no combiner
relaxation, and clear statement that the benchmark is not a clinical truth set.

### 5. Real-World Validation

Goal: expand offline real-world smoke coverage and establish a stronger
validation protocol using curated real variants and local fixtures.

Why it matters: noisy and incomplete real-world records reveal integration
failures that synthetic cases miss. Validation must remain careful because
concordance with external assertions is not the same as clinical correctness.

Architecture impact: expected changes should be concentrated in fixtures,
smoke tests, documentation, and report review. Provider behavior should remain
conservative.

Safety risks: ClinVar concordance pressure can tempt unsafe direct assertion
reuse. Real data must not cause candidate ClinVar or literature evidence to
enter applied classification automatically.

Expected deliverables: larger real-data smoke suite, local source provenance,
allowed conservative outcomes, context conflict examples, and review notes for
discordant cases.

Release gate expectations: smoke pass, full pytest pass, no network dependency,
no candidate leakage, and documentation of unresolved validation limitations.

### 6. Chinese Report Template

Goal: provide a Chinese-language report template that preserves the same safety
wording, applied/candidate separation, provenance, limitations, and
review-required posture as the existing reports.

Why it matters: report usability improves when reviewers can read safety
language and evidence summaries in the language of their workflow.

Architecture impact: expected changes should be in reporting templates,
formatting, localization wording, and report tests. It must not change
classification behavior.

Safety risks: translated wording must not imply clinical sign-out, certainty,
or automatic evidence application. VUS caution and human review requirements
must remain explicit.

Expected deliverables: Chinese Markdown/report output, terminology glossary,
report tests, and documentation showing parity with English safety sections.

Release gate expectations: report wording safety review by a qualified reader,
pytest pass, smoke report generation, and no changes to evidence logic or the
combiner.

## Tasks Not Appropriate For The Current Stage

The following tasks should not be implemented in the current beta-stage roadmap
unless the project explicitly enters a validated clinical-development phase with
new data, governance, and review resources:

- CNV/SV interpretation, including DMD complex SV workflows. These require new
  variant models, interval/breakpoint normalization, dosage or mechanism
  evidence, and separate validation.
- Repeat expansion workflows. These require disease-specific repeat units,
  thresholds, inheritance context, and specialized reporting.
- Mitochondrial interpretation. This requires heteroplasmy, tissue context,
  mitochondrial-specific rules, and specialized evidence models.
- Methylation evidence. This requires assay-specific validation and disease
  context not present in the current SNV/small-indel pipeline.
- Automatic PS3/BS3 from literature or predictors. Functional evidence requires
  validated assays and manual review; computational prediction is not
  functional evidence.
- Automatic PS2/PM6/PP1/PS4 from literature. These require trio/family/cohort
  evidence, parentage, segregation counts, phenotype specificity, deduplication,
  and qualified human review.
- Fully automated disease-specific VCEP interpretation. VCEP profiles require
  explicit profile versioning, validation, and disease-specific review.
- Clinical sign-out. The current system is a review-support and proposal tool,
  not a final reporting authority.

Tasks involving trio/family/cohort evidence, wet-lab functional assays, RNA
validation, or disease-specific clinical rules should remain candidate-only or
design-only until real validation data and review governance exist.
