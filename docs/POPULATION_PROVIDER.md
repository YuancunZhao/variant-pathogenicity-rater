# Population Provider

Population frequency lookup is offline by default. The packaged configuration keeps the
`population` source in `mock` mode and does not perform network requests. The provider layer
only retrieves and normalizes population-frequency facts; BA1, BS1, and PM2 decisions must still
flow through `variant_pathogenicity_rater.acmg.population_rules`.

## Local File Mode

Set the population data source to `local_file` and point `local_file` to a checked local snapshot.
JSON arrays, `{"records": [...]}` JSON objects, and JSONL files are supported. JSONL is the
recommended first format because each line is an independent gnomAD-like record.

Example JSONL record:

```json
{"variant_key":"1-100-A-G","genome_build":"GRCh38","dataset_version":"gnomad-like-test-v1","overall_af":0.0,"max_pop_af":0.0,"population_name":"global","allele_count":0,"allele_number":100000,"homozygote_count":0,"hemizygote_count":0,"faf95":0.0,"filtering_af":0.0,"coverage_quality":"high","population_match":true}
```

Records are queried by normalized `chromosome-position-ref-alt` keys, ignoring a leading `chr`.
When coordinates do not match, the provider can fall back to `gene + hgvs_c` or `gene + hgvs_p`.
Genome build mismatches are treated as limitations, not as usable frequency evidence.

## Provenance

Every returned `PopulationFrequency` includes an `EvidenceSource` with provenance metadata:
`data_source`, `source_version`, `genome_build` through the frequency payload, query, retrieval
time, raw-record hash, parser version, population/ancestry, allele number, coverage quality, and
limitations. Local-file misses also return provenance and an explicit limitation.

## Safety Behavior

No local record found is not equivalent to absence from population databases. A miss returns no AF,
`is_absent=false`, and a limitation; it must not trigger PM2 automatically.

Population evidence is downgraded to candidate-only when quality or context is insufficient,
including low allele number, low coverage, ancestry mismatch, missing disease prevalence, missing
penetrance configuration, missing inheritance mode, founder-population warnings, malformed records,
and unavailable AF/AN data.

True zero AF can support `PM2_Supporting` only after `population_rules` sees usable frequency data,
sufficient allele number, no explicit low coverage or ancestry mismatch, and complete disease
context. High AF can apply BA1/BS1 only under the same rule-gated safety checks. Providers never
bypass these rules.

## Future gnomAD Integration

A future online gnomAD provider should map API responses into the same `PopulationFrequency`
schema and preserve the same provenance fields. It should keep the existing offline default, require
an explicit online opt-in, cache raw payloads, record dataset/build/version details, and continue to
delegate all BA1/BS1/PM2 decisions to `population_rules`.
