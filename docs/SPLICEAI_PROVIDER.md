# SpliceAI Local-File Provider

The SpliceAI provider is an optional local-file source for SNV and small-indel computational evidence. It is not enabled by default and never performs network access.

## Scope

- Reads pre-annotated SpliceAI records from a local JSONL or TSV file.
- Matches records by chromosome, position, reference allele, and alternate allele.
- Emits structured `SplicePrediction` data and a `ComputationalPrediction` wrapper for PP3/BP4 evaluation.
- Contributes only to computational evidence. It cannot trigger PS3, BS3, or PVS1.
- Does not replace RNA, minigene, functional, segregation, population, ClinVar, or PVS1 evidence.
- Does not override the PVS1 engine. Canonical splice variants remain handled conservatively by PVS1.

## Enabling

Default configuration uses offline mock computational predictions. To use a local SpliceAI snapshot, explicitly set the computational source to `local_file` and provide a path:

```json
{
  "options": {
    "data_sources": {
      "sources": {
        "computational": {
          "mode": "local_file",
          "local_file": "data/fixtures/spliceai.jsonl",
          "source_version": "SpliceAI-local-snapshot-v1"
        }
      }
    }
  }
}
```

Environment overrides use the computational provider keys:

```text
VPR_COMPUTATIONAL_MODE=local_file
VPR_COMPUTATIONAL_LOCAL_FILE=/path/to/spliceai.tsv
```

No online SpliceAI provider is implemented.

## JSONL Format

Each line is one JSON object:

```json
{"chrom":"1","pos":12345,"ref":"A","alt":"G","genome_build":"GRCh38","DS_AG":0.82,"DS_AL":0.01,"DS_DG":0.02,"DS_DL":0.03,"max_delta_score":0.82,"predicted_consequence":"splice altering","affected_gene":"GENE1","transcript":"NM_000001.1","source_version":"SpliceAI-1.3.1-local"}
```

## TSV Format

The TSV header should contain the same fields:

```text
chrom	pos	ref	alt	genome_build	DS_AG	DS_AL	DS_DG	DS_DL	max_delta_score	predicted_consequence	affected_gene	transcript	source_version
1	12345	A	G	GRCh38	0.82	0.01	0.02	0.03	0.82	splice altering	GENE1	NM_000001.1	SpliceAI-1.3.1-local
```

Accepted coordinate aliases include `chromosome`, `position`, `reference`, and `alternate`.

## Output Fields

The provider preserves these SpliceAI fields:

- `DS_AG`
- `DS_AL`
- `DS_DG`
- `DS_DL`
- `max_delta_score`
- `predicted_consequence`
- `affected_gene`
- `transcript`
- `source_version`
- `genome_build`
- `provenance`

## Safety Behavior

- High `max_delta_score` can contribute at most PP3 supporting, and only through computational evidence.
- Low `max_delta_score` can contribute to BP4 supporting only when another benign computational predictor agrees.
- Conflicting SpliceAI score/consequence calls do not trigger PP3 or BP4; they emit a review flag.
- Transcript mismatch is candidate-only.
- Genome build mismatch is candidate-only and reported as a limitation.
- No local record means no computational evidence is triggered.
- SpliceAI cannot trigger PS3, BS3, or PVS1 and cannot upgrade PVS1.

