# Variant Pathogenicity Rater

Current version: v0.3.0 internal release.

Codex Plugin plus MCP server framework for SNV/small indel ACMG variant interpretation tools.
Variant Pathogenicity Rater is a semi-automated ACMG interpretation assistant,
not a clinical sign-out system. The current v0.3.0 workflow supports
an offline, mock-backed end-to-end `rate_variant` loop: natural-language input
wrappers, normalization, variant resolution, annotation/context consistency,
automatic applied evidence generation,
candidate/suggested evidence, manual reviewed evidence, ACMG classification
combining, and report generation.

Current automatic applied evidence generation covers PVS1, BA1, BS1,
PM2_Supporting, PP3, BP4, PS1, and PM5. Curator-reviewed `reviewed_applied`
records can also supply applied evidence such as PS3, BS3, PS2, PM6, PP1, PS4,
PP4, and PM3. Literature and ClinVar suggestions do not apply evidence by
themselves. v0.3.0 adds comparator-based PS1/PM5 generation, manual reviewed
evidence intake, literature-to-reviewed draft workflow, ClinGen ERepo
review-note integration, natural-language input, offline variant resolution,
VCEP signal/override review context, real provider validation, a 100-case
offline benchmark, opt-in online ClinVar/gnomAD/Ensembl VEP/PubMed/LitVar
provider adapters, and Chinese laboratory-internal reports around the existing
safety boundaries.

All conclusions are machine proposals and always require qualified human review. The default workflow does not use the network.

Online provider support is disabled by default. Explicit CLI/MCP options can
enable ClinVar, gnomAD, Ensembl VEP, PubMed, or LitVar adapters, but provider
records remain auditable facts or review notes. Providers do not create applied
evidence and do not modify the ACMG combiner. See
`docs/REAL_PROVIDER_PIPELINE.md` and `docs/ONLINE_PROVIDER_SAFETY.md`.

Optional live provider smoke validation is available for reachability,
payload-compatibility, cache/provenance, and failure-to-limitation checks. It
is skipped by default and requires an explicit environment gate:

```bash
VPR_RUN_LIVE_PROVIDER_SMOKE=1 \
VPR_LIVE_PROVIDER_CACHE_DIR=/tmp/vpr_live_provider_cache \
VPR_LIVE_PROVIDER_TIMEOUT=10 \
PYTHONPYCACHEPREFIX=/private/tmp/vpr_pycache \
.venv/bin/python -m pytest tests/test_live_provider_smoke.py -m "online_clinvar_smoke or online_gnomad_smoke or online_vep_smoke or online_literature_smoke"
```

LitVar live smoke is optional/experimental and additionally requires
`VPR_RUN_LIVE_LITVAR_SMOKE=1`. See
`docs/LIVE_PROVIDER_SMOKE_VALIDATION.md`.

Real-world HGVS smoke validation is also available through
`data/real_world_smoke_variants_v1.json` and
`tests/test_real_world_variant_smoke_validation.py`. This suite checks that six
real HGVS c. inputs and one natural-language wrapper input return structured,
auditable results in the default no-network path. It is not a clinical truth
benchmark and does not define expected classifications. Optional online outcome
counting is skipped unless `VPR_RUN_REAL_WORLD_ONLINE_SMOKE=1` is set. See
`docs/REAL_WORLD_VARIANT_SMOKE_VALIDATION.md`.

78B adds a descriptive HGVS resolution provider contract and local real-world
resolution fixture coverage for the same smoke dataset. It improves
protein/consequence/coordinate resolution without changing evidence generation
or the ACMG combiner. See `docs/HGVS_RESOLUTION_PROVIDER.md`.

## Directory Structure

```text
.
├── README.md
├── plugin.toml
├── pyproject.toml
└── mcp-server
    ├── config.py
    ├── server.py
    └── tools
        ├── __init__.py
        ├── health.py
        └── rate_variant.py
```

## Features

- Python 3.11+
- Modular tool registry
- Dynamic tool discovery through `register_tools(registry)`
- Structured JSON logging to stderr
- Async-ready tool handlers
- Structured tool and server errors
- Environment-variable based configuration
- stdio JSON-RPC transport callable by a Codex Plugin
- Integrated offline `rate_variant` pipeline with audit trail and limitations
- Opt-in online provider adapters with shared cache/provenance/failure handling
- JSON output suitable for direct Codex display

## Installation

From a fresh checkout, create a virtual environment and install the package with
development dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

This editable install is the expected setup for internal v0.3.0 testing. It
installs the package from `src/`, the MCP server dependencies, and `pytest`.

Validate the environment:

```bash
.venv/bin/python scripts/check_env.py
.venv/bin/python -m pytest
```

## MCP Tools

Implemented tools:

- `health_check`
- `rate_variant`
- `parse_variant_text`
- `rate_variant_from_text`
- `rate_variant_batch`
- `rate_annotated_variants`
- `normalize_variant`
- `query_clinvar` through an offline mock provider
- `query_population_frequency`
- `evaluate_population_rules`
- `evaluate_computational_evidence`
- `search_literature_evidence`
- `search_and_summarize_literature`
- `assess_literature_evidence`
- `create_reviewed_evidence_draft`
- `evaluate_pvs1`
- `generate_report`

Evidence tools return structured evidence or review-note payloads and a mandatory human-review notice. Literature evidence is candidate-only and never auto-applies PS3, BS3, PS2, PM6, PP1, PS4, or PP4.

`search_and_summarize_literature` provides the broader literature workflow for
caller-supplied records from local fixtures, Codex, or Life Science Research.
It preserves PMID/DOI/title/abstract/source/provenance, collapses duplicates,
summarizes PS3/BS3, PS2/PM6, PP1, PS4, PM3, PP4, PS1/PM5, PM1, and PVS1
mechanism support, and returns candidate-only `suggested_evidence` plus
`reviewed_evidence_drafts`.

`parse_variant_text`, `rate_variant_from_text`, and CLI `vpr rate-text` provide
a natural-language/HGVS text wrapper around the existing `rate_variant`
workflow. The default parser is regex/rule-based. It extracts explicit
structured fields, surfaces missing fields and ambiguity warnings, keeps short
aliases such as `185delAG` as review-only `alias_candidates`, and never
generates evidence or changes classification logic. Optional AI-assisted
disease/HPO parsing is opt-in, candidate-only, and requires confirmation before
context is used for rating. See
[docs/NATURAL_LANGUAGE_INPUT.md](docs/NATURAL_LANGUAGE_INPUT.md) and
[docs/AI_ASSISTED_CONTEXT_PARSING.md](docs/AI_ASSISTED_CONTEXT_PARSING.md).

`search_and_summarize_literature` is the general literature search and summary
engine. It accepts caller-supplied records from local fixtures, Codex, or Life
Science Research workflows; builds query templates; collapses duplicates;
summarizes criterion-specific candidate support; and returns
`suggested_evidence` plus non-applied reviewed draft templates. It is offline
by default and never changes final classification. See
[docs/GENERAL_LITERATURE_ENGINE.md](docs/GENERAL_LITERATURE_ENGINE.md).

`assess_literature_evidence` is an optional ACMG literature evidence agent. It is offline by default, produces `suggested_evidence` only, never writes to applied evidence, and never changes final classification. See [docs/ACMG_LITERATURE_AGENT.md](docs/ACMG_LITERATURE_AGENT.md).

`create_reviewed_evidence_draft` converts literature `suggested_evidence` into
manual `reviewed_evidence` draft templates. Drafts default to
`needs_more_info` and require curator edits before any `reviewed_applied`
record can be passed to `rate_variant --reviewed-evidence`. See
[docs/LITERATURE_TO_REVIEWED_WORKFLOW.md](docs/LITERATURE_TO_REVIEWED_WORKFLOW.md).

Manual reviewed evidence is the explicit curator-controlled path for evidence
that is not automatically applied. It supports reviewed application of criteria
such as PS3/BS3, PS2/PM6, PP1, PS4, PP4, and PM3 when a curator supplies a
valid `reviewed_applied` record with rationale, review date, citation or
provenance, and audit trail. Candidate or suggested evidence is never silently
converted into combiner-counted evidence. See
[docs/MANUAL_REVIEWED_EVIDENCE.md](docs/MANUAL_REVIEWED_EVIDENCE.md).

PVS1 is generated by a conservative applied-evidence layer rather than by consequence term alone. Applied PVS1 requires clear LoF consequence, matching gene-disease LoF mechanism, relevant protein-coding transcript, and NMD/splice support; otherwise PVS1 is emitted only as candidate/review-note evidence. See [docs/PVS1_AUTOMATION.md](docs/PVS1_AUTOMATION.md) and [docs/APPLIED_EVIDENCE_GENERATION.md](docs/APPLIED_EVIDENCE_GENERATION.md).

Population BA1/BS1/PM2_Supporting evidence is generated by a conservative
decision layer around the existing population rules. Applied evidence requires
usable AF, sufficient allele number, adequate coverage, matched ancestry and
population context, matching genome build, retained source version, complete
disease context, disease-specific thresholds, penetrance context, and no context
conflict. A provider miss or "no record found" result is never treated as
absence and cannot trigger PM2. See
[docs/POPULATION_EVIDENCE_AUTOMATION.md](docs/POPULATION_EVIDENCE_AUTOMATION.md).

Computational PP3/BP4 evidence is generated by a Phase 3 consensus layer. REVEL,
CADD, SIFT, PolyPhen, MutationTaster, AlphaMissense, SpliceAI, and placeholders
are treated as parallel predictors; no single predictor can apply evidence or
override conflicts. PP3/BP4 are supporting-only, always require review, and
conflicts or insufficient predictors remain candidate-only. SpliceAI is not
functional evidence or RNA validation and cannot trigger PS3, BS3, or PVS1. See
[docs/COMPUTATIONAL_EVIDENCE_AUTOMATION.md](docs/COMPUTATIONAL_EVIDENCE_AUTOMATION.md).

ClinVar-derived PS1/PM5 evidence is generated only through strict comparator
checks. PS1 requires the same amino acid change from a confirmed different
nucleotide change; PM5 requires a different pathogenic missense change at the
same residue. Both require matched disease condition, matched transcript/protein
context, high-quality non-conflicting germline ClinVar P/LP comparator records,
provenance, and human review. ClinVar assertions alone do not trigger PP5/BP6 or
determine classification. See
[docs/PS1_PM5_AUTOMATION.md](docs/PS1_PM5_AUTOMATION.md).

## Reports

`generate_report` renders an existing `ClassificationResult` as markdown,
plain text, or JSON in `concise`, `detailed`, `laboratory`, or `clinician`
mode. Reporting is presentation-only: it does not add ACMG criteria, rerun the
combiner, relax safety rules, or change the final classification.

Reports separate:

- final machine proposal
- applied ACMG evidence
- candidate/review-note evidence
- manual reviewed evidence
- context consistency
- transcript selection
- data sources/provenance
- limitations and safety notes

ClinVar and literature notes remain candidate/review-note evidence unless a
separate conservative generator has already emitted applied evidence in the
supplied result. ClinVar-derived PS1/PM5 is labeled as comparator-based,
review-required, and not PP5. SpliceAI is described as computational splice
prediction only, not functional evidence. Transcript selection and context
consistency are review context and are not counted by the classification
combiner. VUS reports use conservative wording and do not imply that the variant
is likely pathogenic.

Chinese laboratory-internal reports are available with `language=zh` or the CLI
`--output markdown-zh` shortcut. They keep the same presentation-only boundary:
no ACMG criteria are added, no evidence generation is rerun, and the combiner is
not changed. Chinese reports preserve applied evidence, candidate/review-note
evidence, manual reviewed evidence, provenance, limitations, and human-review
checklists, and state that the output is a machine proposal rather than a final
clinical conclusion.

See [docs/REPORTING.md](docs/REPORTING.md) for section definitions, JSON keys,
batch summary fields, and safety wording.

## CLI

The `vpr` command provides terminal access to the same offline/mock-backed single
variant, batch, annotated-batch, and environment-check workflows:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown-zh
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown --language zh --report-mode laboratory
vpr batch --input variants.jsonl --format jsonl
vpr annotated-batch --input vep.tsv --source vep --include-report
vpr check-env
```

See [docs/CLI.md](docs/CLI.md) for command options and output behavior.

## Start

After installation, start the MCP server with the same virtual environment
Python used for tests:

```bash
.venv/bin/python mcp-server/server.py
```

The server uses stdio JSON-RPC. Example request:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' | .venv/bin/python mcp-server/server.py
```

Health check:

```bash
printf '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"health_check","arguments":{}}}\n' | .venv/bin/python mcp-server/server.py
```

Integrated workflow call:

```bash
printf '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"rate_variant","arguments":{"gene":"BRCA1","transcript":"NM_007294.4","hgvs_c":"NM_007294.4:c.68_69delAG","hgvs_p":"NP_009225.1:p.Glu23ValfsTer17","chromosome":"17","position":43092919,"ref":"AG","alt":"A","disease":"Hereditary breast and ovarian cancer","inheritance":"autosomal dominant","phenotype":["HP:0003002"]}}}\n' | .venv/bin/python mcp-server/server.py
```

The `rate_variant` output includes:

- `classification_result`: a Pydantic-derived `ClassificationResult` payload
- `evidence_items`: all applied or candidate evidence items
- `applied_evidence`: evidence counted by the supplied classification result
- `review_note_evidence`: candidate/review-note evidence excluded from the combiner
- `normalization_identity`: stable normalized identity metadata from normalization
- `mock_mode`: backward-compatible legacy flag; it is not per-provider outcome
  status
- `offline_default_mode`: whether the loaded data-source configuration remains
  offline by default
- `data_source_modes`: configured/requested provider modes after options are
  applied
- `data_source_modes_semantics`: reminder that `data_source_modes` is not an
  outcome summary
- `provider_mode_summary`: actual provider outcomes by source, including
  requested/configured mode, success/no-record/failure/skipped/cache-hit
  outcome, source version, endpoint, query, raw hash, cache hit, provider mode,
  record count, and limitations
- `unresolved_placeholder_mode`: whether resolution or provider outputs still
  contain unresolved placeholder state
- `transcript_selection`: transcript recommendation context, when supplied
- `context_consistency`: context checks, when available
- `final_classification`: one of `pathogenic`, `likely_pathogenic`, `vus`, `likely_benign`, `benign`
- `review_flags`: review flags carried from classification, transcript selection, and context checks
- `provenance`: normalization, evidence-source, transcript-selection, and context-check provenance
- `report_text`: rendered detailed report text
- `limitations`: module warnings and any failed-step messages
- `human_review_required`: always `true`
- `audit_trail`: started/completed/failed events for every pipeline step
- `step_results`: serialized per-step outputs

Example files:

- `examples/rate_variant_input.json`
- `examples/rate_variant_output.json` (representative shortened JSON summary)

Mock database fixtures can be supplied under `options`, including
`population_frequency`, `computational_predictions`, `clinvar_records`, and
`literature_records`. When omitted, deterministic offline fixtures are used.

Batch rating is available through `rate_variant_batch`. It accepts JSON arrays,
JSONL, CSV/TSV, and minimal VCF-like TSV input, calls the existing `rate_variant`
pipeline independently for each SNV/small-indel record, and reports malformed or
unsupported rows in `failed_records` instead of skipping them silently. See
`docs/BATCH_INPUT.md`.

Batch results include a `summary` object with total, succeeded, failed,
classification distribution, review-required count, context conflict count,
failed-record summaries, and duplicate warnings. The summary is for triage only
and does not override per-record classification or review requirements.
Successful batch records expose the same integration fields as single-variant
rating using per-record names: `applied_evidence`, `review_note_evidence`,
`normalization_identity`, `transcript_selection_summary`,
`context_consistency_summary`, `review_flags`, `provenance`, and `limitations`.

Normalize a VCF-like SNV or small indel:

```bash
printf '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"normalize_variant","arguments":{"input_type":"vcf_like","chrom":"13","pos":32316461,"ref":"AT","alt":"A","gene_symbol":"BRCA2","transcript":"NM_000059.4","hgvs_c":"NM_000059.4:c.5946delT","hgvs_p":"NP_000050.3:p.Ser1982ArgfsTer22","genome_build":"GRCh38"}}}\n' | .venv/bin/python mcp-server/server.py
```

Normalize an HGVS-like input:

```bash
printf '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"normalize_variant","arguments":{"gene":"BRCA1","transcript":"NM_007294.4","hgvs_c":"NM_007294.4:c.68A>G","hgvs_p":"NP_009225.1:p.Lys23Arg","genome_build":"GRCh38"}}}\n' | .venv/bin/python mcp-server/server.py
```

HGVS-like inputs preserve `transcript`, `hgvs_c`, and `hgvs_p`. Because phase 1 does not perform liftover, transcript mapping, or external API normalization, genomic fields that cannot be resolved locally are returned in `unresolved_fields`, accompanied by `normalization_warnings`, and `human_review_required` is always `true`.

For structured inputs that already include genome build, chromosome, position,
ref, and alt, `variant_resolution.resolved_coordinate` preserves the normalized
coordinate even when no local transcript-resolution fixture is available. When
online VEP is explicitly requested, VEP transcript consequences may populate
descriptive `variant_resolution.resolved_hgvs_p` and consequence fields. These
resolution facts are review context only; they do not create applied evidence.

Example JSON files live in `examples/normalization/`.

## ClinVar Mock Integration

`query_clinvar` supports these offline query shapes:

- `gene` + `hgvs_c`
- `gene` + `hgvs_p`
- `rsid`
- `variation_id`
- `chromosome` + `position` + `ref` + `alt`

Example:

```bash
printf '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"query_clinvar","arguments":{"query":{"gene":"BRCA1","hgvs_c":"NM_007294.4:c.68_69delAG"}}}}\n' | .venv/bin/python mcp-server/server.py
```

The response includes `clinvar_records`, `candidate_evidence_items`, `review_flags`, and `limitations`. ClinVar P/LP assertions with higher review status are emitted as candidate review notes for possible PS1/PM5/PP5 consideration. In the integrated `rate_variant` workflow, a separate PS1/PM5 comparator generator may emit review-required PS1/PM5 only after strict protein, nucleotide, transcript/protein, condition, quality, conflict, and provenance gates pass. Benign/likely benign assertions are emitted as benign candidate notes. PP5 and BP6 are not automatically applied, and conflicting interpretations are blocking manual-review flags.

Optional ClinVar online mode is documented in `docs/CLINVAR_PROVIDER.md`. It is disabled by default, requires both `mode=online` and `online_enabled=true`, and still emits ClinVar assertions only as candidate/review-note evidence rather than applied ACMG criteria.

Mock data currently covers BRCA1 `NM_007294.4:c.68_69delAG`, CFTR `NM_000492.4:c.1521_1523delCTT`, HBB `rs334`, and a likely benign `GENE1` fixture. The example input lives at `examples/clinvar_query_input.json`, and representative fixture records live at `examples/clinvar_mock_records.json`.

## Optional ClinVar Online Provider

ClinVar online lookup is available through `ClinVarOnlineProvider`, but it is opt-in only. The default configuration remains `mock` and does not perform network requests. Setting only `VPR_CLINVAR_MODE=online` is not enough; online access also requires `VPR_CLINVAR_ONLINE_ENABLED=true`.

Example opt-in configuration:

```bash
export VPR_CLINVAR_MODE=online
export VPR_CLINVAR_ONLINE_ENABLED=true
export VPR_CLINVAR_TIMEOUT_SECONDS=10
export VPR_CLINVAR_EMAIL=curator@example.org
export VPR_CLINVAR_USER_AGENT="variant-pathogenicity-rater/0.3.0 curator@example.org"
```

`VPR_CLINVAR_MODE=future_online` is accepted as an alias for the current online provider when `VPR_CLINVAR_ONLINE_ENABLED=true` is also present. Online query results are stored in the disk cache configured by `cache_dir` and `ttl_seconds`; cache hits reuse the cached payload and preserve provenance metadata.

Supported online query shapes:

- `gene` + `hgvs_c`
- `gene` + `hgvs_p`
- `variation_id`
- `rsid`
- `chromosome` + `position` + `ref` + `alt` placeholder query

Online ClinVar records include provenance fields for the query, source version, retrieval time, raw record hash, parser version, source URL or endpoint, review status, and last evaluated date. The parser extracts clinical significance, review status, review-star confidence, condition, submitter count, conflict status, citations, and germline/somatic classification.

Safety behavior is intentionally conservative: conflicting interpretations, condition mismatch, old submissions, single submitter or no assertion criteria, and non-germline assertions produce review flags. Expert panel and practice guideline records receive higher confidence metadata but remain candidate-only. Somatic-only records are not emitted as germline ACMG candidates. ClinVar assertions never auto-trigger PP5/BP6 and cannot determine the final classification by themselves. If an online request fails or times out, `rate_variant` records the issue in `limitations` and continues.

## ACMG Classification Combiner

The combiner lives in `variant_pathogenicity_rater.acmg.combiner` and only combines already-triggered `EvidenceItem` records. It does not retrieve external data and does not decide whether evidence criteria should trigger.

```python
import json

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.schemas import EvidenceItem, GeneDiseaseContext, Variant

payload = json.loads(open("examples/acmg_classification_input.json").read())
variant = Variant.model_validate(payload["variant"])
context = GeneDiseaseContext.model_validate(payload["gene_disease_context"])
evidence_items = [
    EvidenceItem.model_validate(item)
    for item in payload["evidence_items"]
]

result = classify_acmg(evidence_items, variant, context)
print(result.model_dump_json(indent=2))
```

The output is a `ClassificationResult` with `applied_combination_rule`, pathogenic and benign evidence summaries, `conflicting_evidence`, `limitations`, and `human_review_required`.

Example files:

- `examples/acmg_classification_input.json`
- `examples/acmg_classification_output.json`

## Mock Literature Evidence

The first literature phase is offline-only. `search_literature_evidence` uses `MockLiteratureProvider` and returns citation-preserving literature records, extracted claims, candidate evidence items, review flags, and limitations.

The general literature workflow is available through
`search_and_summarize_literature` and CLI `vpr literature-search`. It accepts
caller-supplied literature records, preserves citation/provenance fields,
deduplicates publications or families, summarizes all literature-dependent ACMG
criteria for manual review, and emits only candidate suggestions and
non-applied draft templates.

Supported candidate evidence hints:

- Functional evidence: PS3 / BS3 candidates
- De novo evidence: PS2 / PM6 candidates
- Segregation: PP1 candidates
- Case reports: PS4 candidate hints
- Phenotype specificity: PP4 candidate hints

These are never applied as criteria in this phase. Candidate items use `strength: "none"`, set `requires_review: true`, include a `citation`, and set `supporting_data.automatic_application` to `false`. Duplicate studies are collapsed by PMID, DOI, or study ID to avoid repeated counting.

Mock literature request:

```bash
printf '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"search_literature_evidence","arguments":{"variant":{"variant_id":"GRCh38-1-123-A-G","genome_build":"GRCh38","variant_type":"snv","chrom":"1","pos":123,"ref":"A","alt":"G","gene_symbol":"GENE1","hgvs_c":"NM_000001.1:c.76A>G","hgvs_p":"NP_000001.1:p.Lys26Arg"},"gene_disease_context":{"gene_symbol":"GENE1","disease_name":"GENE1-related example disorder","inheritance_mode":"autosomal dominant","phenotype_terms":["HP:0001250","HP:0001263"]}}}}\n' | .venv/bin/python mcp-server/server.py
```

Example files:

- `examples/literature_mock_input.json`
- `examples/literature_mock_output.json`

## Configuration

Data source defaults are checked in at
`src/variant_pathogenicity_rater/config/data_sources.yaml`. The default mode is
offline `mock` for ClinVar, population, literature, and computational sources.
Online ClinVar requires explicit opt-in with both mode and gate enabled; setting
only `VPR_CLINVAR_MODE=online` does not permit network use.

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VPR_SERVER_NAME` | `variant-pathogenicity-rater` | MCP server name |
| `VPR_SERVER_VERSION` | `0.3.0` | MCP server version |
| `VPR_LOG_LEVEL` | `INFO` | Structured log level |
| `VPR_TOOLS_PACKAGE` | `tools` | Python package used for dynamic discovery |
| `VPR_ENABLE_HEALTH_TOOL` | `true` | Enable `health_check` |
| `VPR_ENVIRONMENT` | `development` | Runtime environment label |
| `VPR_DATA_SOURCE_MODE` | unset | Override all data sources, for example `mock` or `local_file` |
| `VPR_CLINVAR_MODE` | `mock` | ClinVar provider mode |
| `VPR_CLINVAR_ONLINE_ENABLED` | `false` | Required second gate for online ClinVar |
| `VPR_CLINVAR_LOCAL_FILE` | unset | Local ClinVar snapshot path |
| `VPR_CLINVAR_TIMEOUT_SECONDS` | `10` | Online ClinVar timeout after explicit opt-in |
| `VPR_CLINVAR_EMAIL` | unset | Optional NCBI identity email |
| `VPR_CLINVAR_USER_AGENT` | unset | Optional ClinVar user agent |
| `VPR_POPULATION_MODE` | `mock` | Population provider mode |
| `VPR_POPULATION_LOCAL_FILE` | unset | Local population snapshot path |
| `VPR_COMPUTATIONAL_MODE` | `mock` | Computational provider mode; `local_file` enables local SpliceAI-style files |
| `VPR_COMPUTATIONAL_LOCAL_FILE` | unset | Local computational or SpliceAI snapshot path |
| `VPR_LITERATURE_MODE` | `mock` | Literature provider mode |
| `VPR_LITERATURE_LOCAL_FILE` | unset | Local literature snapshot path |

Provider-specific documentation:

- `docs/CLINVAR_PROVIDER.md`
- `docs/POPULATION_PROVIDER.md`
- `docs/SPLICEAI_PROVIDER.md`

## Codex Plugin

`plugin.toml` declares the Codex Plugin entry point and starts the MCP server
over stdio with:

```text
.venv/bin/python mcp-server/server.py
```

For internal testing, install the project first, then enable this repository as
a local Codex Plugin. The plugin uses dynamic MCP tool discovery from
`mcp-server/tools` and should expose the same tool list shown by
`tools/list`.

## Testing

Create a local virtual environment and install the development extras:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Run the integration and smoke tests with the project virtual environment:

```bash
.venv/bin/python -m pytest
```

You can also use the repository test wrapper, which always runs pytest through
the virtual environment Python instead of relying on a `pytest` executable in
the shell `PATH`:

```bash
scripts/test.sh
```

Diagnose the active environment:

```bash
.venv/bin/python scripts/check_env.py
```

Run with coverage once `pytest-cov` is installed:

```bash
.venv/bin/python -m pytest --cov=variant_pathogenicity_rater --cov=mcp-server --cov-report=term-missing
```

The pytest and coverage settings live in `pyproject.toml`. The `dev` optional
dependency group includes `pytest`; the legacy `test` extra is kept for
compatibility. Coverage support is isolated in the `coverage` extra so the
standard test environment remains minimal and reproducible. The suite covers
schema validation, normalization, population rules, computational PP3/BP4 rules,
ClinVar and literature mock providers, PVS1, classification combinations,
report generation, and MCP smoke paths. The `tests/test_rate_variant_pipeline.py`
integration tests cover the direct Python pipeline, failure-as-limitation
behavior, and the MCP `rate_variant` tool.

## Tool Registration Example

Create a module under `mcp-server/tools`, for example `mcp-server/tools/my_tool.py`:

```python
from tools import ToolDefinition, ToolRegistry


async def handler(arguments: dict) -> dict:
    return {"status": "ok", "received": arguments}


def register_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="my_tool",
            description="Example custom tool.",
            input_schema={
                "type": "object",
                "properties": {
                    "variant": {"type": "string"}
                },
                "required": ["variant"],
                "additionalProperties": False,
            },
            handler=handler,
        )
    )
```

Any module exposing `register_tools(registry)` is discovered automatically at startup.
