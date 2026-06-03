# Real Provider Pipeline

The real provider pipeline adds opt-in online adapters for ClinVar, gnomAD,
Ensembl VEP, PubMed, and LitVar. These adapters retrieve and normalize provider
records into the existing Variant Pathogenicity Rater data-source layer.

Online providers are disabled by default. Default test and CLI behavior remains
offline/mock/local and does not require network access.

## Architecture

Online providers are fact providers, not ACMG classifiers:

- ClinVar online records normalize to `ClinVarRecord`.
- gnomAD online records normalize to `PopulationFrequency`.
- Ensembl VEP online records normalize to computational prediction and
  transcript/consequence records.
- PubMed and LitVar online records normalize to literature-engine
  `LiteratureRecord` records.

The ACMG classification combiner is unchanged. Provider output can affect
classification only through existing safety-gated evaluators:

- population facts through population rules;
- computational facts through PP3/BP4 computational rules;
- ClinVar comparator facts through PS1/PM5 comparator generation;
- literature records through candidate-only literature summaries and reviewed
  drafts.

ClinVar assertions, ClinGen ERepo records, and literature records remain
non-applied unless a curator later submits valid `reviewed_applied` evidence.

## Providers

### ClinVar

The ClinVar online provider uses NCBI EUtils query shapes for Variation ID,
rsID, HGVS, genomic coordinates, and comparator-oriented gene queries. It
normalizes review status, star level, condition, germline/somatic context,
clinical significance, submitter count, last evaluated date, conflict status,
citations, and provenance into `ClinVarRecord`.

ClinVar never emits applied PP5/BP6. Exact records are review notes, and
same-residue or same-amino-acid records can only support PS1/PM5 through the
existing comparator generator.

### gnomAD

The gnomAD online provider uses GraphQL variant lookup and maps AC, AN, AF,
homozygote/hemizygote counts, population counts, popmax, FAF, dataset version,
and query provenance into `PopulationFrequency`.

A missing gnomAD record is a limitation only. It is not interpreted as
population absence and cannot trigger PM2 by itself.

### Ensembl VEP

The Ensembl VEP online provider parses transcript consequences, HGVS
protein/coding/genomic fields where available, protein consequence,
canonical/MANE-like tags when present in the payload, and supported predictor
fields including CADD, REVEL, SIFT, PolyPhen, MutationTaster, AlphaMissense,
and SpliceAI.

Missing predictors become limitations. VEP does not directly apply PP3/BP4.

### PubMed and LitVar

PubMed and LitVar online adapters feed the General Literature Search and
Summary Engine. They retrieve metadata and abstracts where available, preserve
provider provenance, and mark abstract-only records as requiring manual review.

Literature output remains suggested/reviewed-draft material only. It is never
added to applied ACMG evidence automatically.

## Audit Data

Provider outputs preserve:

- provider/source name;
- source version or live-source label;
- retrieval timestamp;
- normalized query;
- endpoint or source URL;
- parser version;
- raw payload hash;
- cache hit status when available;
- limitations and review flags.

Provider failures, timeouts, malformed responses, empty results, low-quality
population data, build mismatch, ancestry mismatch, stale source metadata, and
unsupported predictor fields degrade to limitations instead of aborting the
main workflow.
