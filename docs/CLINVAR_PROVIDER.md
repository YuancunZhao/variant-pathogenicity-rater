# ClinVar Provider

ClinVar is offline by default. The packaged configuration uses mock/local data unless a caller explicitly sets the ClinVar source to `online` and also sets `online_enabled=true`.

## Enabling Online Mode

Online mode can be enabled per `rate_variant` call:

```json
{
  "options": {
    "data_sources": {
      "clinvar": {
        "mode": "online",
        "online_enabled": true,
        "cache_dir": ".cache/variant_pathogenicity_rater/clinvar",
        "email": "curator@example.org"
      }
    }
  }
}
```

It can also be enabled with environment variables:

```bash
VPR_CLINVAR_MODE=online
VPR_CLINVAR_ONLINE_ENABLED=true
VPR_CLINVAR_EMAIL=curator@example.org
```

The explicit `online_enabled=true` gate is required so routine tests and clinical review workflows do not accidentally use the network. Validation tests for online behavior use mocked HTTP responses only.

## Safety Contract

ClinVar assertions never directly determine the final ACMG classification in this project.

- ClinVar-derived `EvidenceItem` records are candidate/review-note only.
- ClinVar candidate items use `strength=none`, `candidate_only=true`, `evidence_status=candidate`, and `applied=false`.
- PP5 and BP6 are not automatically triggered.
- PS1 and PM5 require independent variant/protein-level assessment before use.
- Somatic-only ClinVar records are not emitted as germline ACMG candidates.
- Conflicting interpretations and condition mismatches produce manual-review flags.

The ACMG combiner logic must remain independent of ClinVar retrieval. ClinVar may appear in the candidate/review-note report section, but not in applied evidence unless a separate reviewed evidence source explicitly creates valid ACMG evidence.

## Parsed Fields

The online provider parses mocked or E-utilities-style summary payloads into `ClinVarRecord` fields:

- `variation_id`
- `clinical_significance`
- `review_status`
- `review_stars` and `review_confidence`
- `condition` and `conditions`
- `submitter_count`
- `last_evaluated`
- `conflicting_interpretations` and `conflict_status`
- `germline_or_somatic`
- `citations`
- source provenance, including endpoint, parser version, query, retrieval time, source URL, and raw-record hash

Supported online query shapes are:

- `gene` + `hgvs_c`
- `gene` + `hgvs_p`
- `rsid`
- `variation_id`
- `chromosome` + `position` + `ref` + `alt`

## Known Limitations

- Online parsing is intentionally conservative and covers the fields needed for review-note use.
- Clinical-significance strings can vary across ClinVar releases and still require human review.
- Condition matching uses simple token overlap; mismatch flags are prompts for review, not final disease-scope adjudication.
- Cache freshness depends on the configured TTL and source version.
- Network failures, invalid queries, and malformed responses are captured as limitations so `rate_variant` can continue.
- ClinVar should not be used as a substitute for primary evidence, laboratory curation, or independent ACMG criterion assessment.
