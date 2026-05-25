from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from variant_pathogenicity_rater.annotation import (
    AnnovarAdapter,
    BcftoolsCsqAdapter,
    GenericTableAdapter,
    VepAdapter,
    evaluate_annotation_safety,
    select_transcript,
)
from variant_pathogenicity_rater.annotation.adapters import AnnotationAdapter, _read_delimited
from variant_pathogenicity_rater.input_cleaning import clean_record, normalize_chromosome_label
from variant_pathogenicity_rater.normalization import NormalizationError, normalize_variant
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation
from variant_pathogenicity_rater.schemas.batch import BatchRecordError, FailedBatchRecord

SUPPORTED_ANNOTATION_FORMATS = {"vep", "annovar", "bcftools", "generic"}


@dataclass(frozen=True)
class ParsedAnnotationRow:
    input_index: int
    raw_record: dict[str, Any]
    annotation: VariantAnnotation


def annotation_to_batch_records(
    annotations: list[VariantAnnotation],
    *,
    input_indices: list[int] | None = None,
    failed_records: list[FailedBatchRecord] | None = None,
    options: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert parsed annotations into records accepted by rate_variant_batch.

    Annotation stays descriptive: it is passed to the existing transcript-selection
    path and never converted directly into ACMG evidence.
    """

    rows = [
        ParsedAnnotationRow(
            input_index=input_indices[index] if input_indices and index < len(input_indices) else index,
            raw_record=annotation.raw_fields,
            annotation=annotation,
        )
        for index, annotation in enumerate(annotations)
    ]
    grouped = _group_annotation_rows(rows)
    batch_records: list[dict[str, Any]] = []
    limitations = [
        "Annotation-derived batch records are descriptive inputs only; annotation does not directly generate ACMG evidence.",
        "Human review remains required for every variant.",
    ]
    review_flags: list[dict[str, Any]] = []

    for group_rows in grouped:
        group_annotations = [row.annotation for row in group_rows]
        safety = evaluate_annotation_safety(group_annotations)
        selection = select_transcript(group_annotations)
        limitations.extend(safety.limitations)
        limitations.extend(selection.limitations)
        review_flags.extend(json.loads(flag.model_dump_json()) for flag in safety.review_flags)
        review_flags.extend(json.loads(flag.model_dump_json()) for flag in selection.review_flags)

        selected_annotation = _selected_annotation(group_annotations, selection.selected_transcript)
        record = _batch_record_from_annotation(selected_annotation, context=context)
        record["_annotation_input_index"] = min(row.input_index for row in group_rows)
        record["options"] = _record_options(
            options or {},
            group_annotations,
            selected_transcript=selection.selected_transcript,
        )
        record["annotation_workflow"] = {
            "source": selected_annotation.annotation_source,
            "input_indices": [row.input_index for row in group_rows],
            "annotation_provenance": [
                json.loads(annotation.provenance.model_dump_json())
                for annotation in group_annotations
            ],
            "annotation_safety": {
                "review_flags": [
                    json.loads(flag.model_dump_json()) for flag in safety.review_flags
                ],
                "limitations": safety.limitations,
            },
            "normalization_identity": _local_normalization_identity(record),
            "transcript_selection_summary": json.loads(selection.model_dump_json()),
            "human_review_required": True,
        }
        batch_records.append(record)

    return {
        "status": "ok",
        "tool": "annotation_to_batch_records",
        "records": batch_records,
        "failed_records": [
            json.loads(record.model_dump_json()) for record in (failed_records or [])
        ],
        "total_annotation_rows": len(annotations) + len(failed_records or []),
        "record_count": len(batch_records),
        "failed_count": len(failed_records or []),
        "review_flags": _unique_dicts(review_flags, key="code"),
        "limitations": _unique(limitations),
        "human_review_required": True,
    }


def run_annotation_batch_workflow(arguments: dict[str, Any]) -> dict[str, Any]:
    parsed_rows, parse_failed, parse_limitations = _parse_annotation_input(arguments)
    converted = annotation_to_batch_records(
        [row.annotation for row in parsed_rows],
        input_indices=[row.input_index for row in parsed_rows],
        failed_records=parse_failed,
        options=dict(arguments.get("options") or {}),
        context=_context(arguments),
    )
    batch = rate_variant_batch(
        {
            "batch_id": arguments.get("batch_id"),
            "records": converted["records"],
            "options": arguments.get("options") or {},
        }
    )
    merged = _merge_annotation_failures(batch, parse_failed)
    merged["tool"] = "rate_annotated_variants"
    merged["stage"] = "annotation_to_batch_records_then_rate_variant_batch"
    merged["annotation_to_batch_records"] = converted
    merged["limitations"] = _unique(
        list(merged.get("limitations") or [])
        + parse_limitations
        + list(converted.get("limitations") or [])
    )
    merged["human_review_required"] = True
    merged["human_review"] = {
        "required": True,
        "notice": "Human review is required. This framework does not provide a final clinical assertion.",
    }
    return merged


def _parse_annotation_input(
    arguments: dict[str, Any],
) -> tuple[list[ParsedAnnotationRow], list[FailedBatchRecord], list[str]]:
    adapter = _adapter(arguments)
    if isinstance(arguments.get("records"), list):
        records = arguments["records"]
    else:
        text = arguments.get("input_text") or arguments.get("text") or arguments.get("data")
        if not isinstance(text, str):
            raise ValueError("Annotated variant workflow requires 'records' or textual annotation input.")
        records = _annotation_rows_from_text(adapter, text, arguments)

    parsed: list[ParsedAnnotationRow] = []
    failed: list[FailedBatchRecord] = []
    limitations: list[str] = []
    if not adapter.source_version:
        limitations.append(
            f"{adapter.source_name} source_version is missing; provenance is incomplete and should be reviewed."
        )
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            failed.append(_malformed_annotation(index, raw, "Annotation record must be an object."))
            continue
        if None in raw:
            failed.append(_malformed_annotation(index, raw, "Delimited annotation row has more fields than the header."))
            continue
        cleaned = clean_record(raw)
        limitations.extend(f"Annotation row {index}: {warning}" for warning in cleaned.warnings)
        try:
            annotation = adapter.normalize_annotation(adapter.parse_record(cleaned.record))
            adapter.validate_annotation(annotation)
        except Exception as exc:  # noqa: BLE001 - row-level failure must be preserved.
            failed.append(
                _malformed_annotation(
                    index,
                    cleaned.record or raw,
                    f"Malformed {adapter.source_name} annotation row {index + 1}: {exc.__class__.__name__}: {exc}",
                )
            )
            continue
        parsed.append(ParsedAnnotationRow(index, cleaned.record, annotation))
    return parsed, failed, limitations


def _annotation_rows_from_text(
    adapter: AnnotationAdapter,
    text: str,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(adapter, VepAdapter) and text.lstrip().startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("VEP JSON annotation input must be an array.")
        return data
    delimiter = arguments.get("delimiter")
    if not isinstance(delimiter, str) or delimiter == "":
        delimiter = "," if isinstance(adapter, GenericTableAdapter) and "\t" not in text.splitlines()[0] else "\t"
    comment_prefix = "##" if isinstance(adapter, VepAdapter) else None
    return _read_delimited(text, delimiter=delimiter, comment_prefix=comment_prefix)


def _adapter(arguments: dict[str, Any]) -> AnnotationAdapter:
    source_format = str(
        arguments.get("annotation_format")
        or arguments.get("source_format")
        or arguments.get("format")
        or "generic"
    ).lower()
    source_version = arguments.get("source_version")
    if source_format not in SUPPORTED_ANNOTATION_FORMATS:
        raise ValueError(f"Unsupported annotation format: {source_format}")
    if source_format == "vep":
        return VepAdapter(source_version=source_version)
    if source_format == "annovar":
        return AnnovarAdapter(source_version=source_version)
    if source_format == "bcftools":
        return BcftoolsCsqAdapter(source_version=source_version)
    return GenericTableAdapter(source_version=source_version)


def _group_annotation_rows(rows: list[ParsedAnnotationRow]) -> list[list[ParsedAnnotationRow]]:
    groups: dict[str, list[ParsedAnnotationRow]] = {}
    for row in rows:
        groups.setdefault(_annotation_group_key(row.annotation), []).append(row)
    return list(groups.values())


def _annotation_group_key(annotation: VariantAnnotation) -> str:
    fields = _genomic_fields(annotation)
    if all(fields.get(key) for key in ("chromosome", "position", "ref", "alt")):
        return f"{fields['chromosome']}:{fields['position']}:{fields['ref']}:{fields['alt']}"
    cleaned_hgvs_c, _ = _clean_hgvs(annotation)
    return cleaned_hgvs_c or annotation.dbsnp_id or f"annotation:{id(annotation)}"


def _batch_record_from_annotation(
    annotation: VariantAnnotation,
    *,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    record.update(_genomic_fields(annotation))
    hgvs_c, hgvs_p = _clean_hgvs(annotation)
    if annotation.gene:
        record["gene"] = annotation.gene
    if annotation.transcript:
        record["transcript"] = annotation.transcript
    if hgvs_c:
        record["hgvs_c"] = hgvs_c
    if hgvs_p:
        record["hgvs_p"] = hgvs_p
    if context:
        record["gene_disease_context"] = context
        for source, target in {
            "disease": "disease",
            "disease_name": "disease",
            "inheritance": "inheritance",
            "inheritance_mode": "inheritance",
            "phenotype_terms": "phenotype_terms",
        }.items():
            if source in context and target not in record:
                record[target] = context[source]
    return {key: value for key, value in record.items() if value not in (None, "")}


def _genomic_fields(annotation: VariantAnnotation) -> dict[str, Any]:
    raw = annotation.raw_fields
    chrom = _pick(raw, "#CHROM", "CHROM", "Chr", "chr", "chrom", "chromosome")
    pos = _pick(raw, "POS", "Start", "start", "position", "pos")
    ref = _pick(raw, "REF", "Ref", "ref")
    alt = _pick(raw, "ALT", "Alt", "alt")
    uploaded = _pick(raw, "Uploaded_variation", "uploaded_variation")
    if uploaded and not all([chrom, pos, ref, alt]):
        parsed = _parse_uploaded_variation(uploaded)
        chrom = chrom or parsed.get("chromosome")
        pos = pos or parsed.get("position")
        ref = ref or parsed.get("ref")
        alt = alt or parsed.get("alt")
    fields: dict[str, Any] = {}
    if chrom:
        fields["chromosome"] = normalize_chromosome_label(chrom)
    if pos:
        try:
            fields["position"] = int(str(pos))
        except ValueError:
            fields["position"] = pos
    if ref:
        fields["ref"] = str(ref)
    if alt:
        fields["alt"] = str(alt)
    if all(key in fields for key in ("chromosome", "position", "ref", "alt")):
        fields["input_type"] = "vcf_like"
    return fields


def _parse_uploaded_variation(value: str) -> dict[str, str]:
    normalized = value.replace("/", "_").replace("-", "_")
    parts = normalized.split("_")
    if len(parts) >= 4:
        return {"chromosome": parts[0], "position": parts[1], "ref": parts[2], "alt": parts[3]}
    return {}


def _clean_hgvs(annotation: VariantAnnotation) -> tuple[str | None, str | None]:
    hgvs_c = annotation.hgvs_c
    hgvs_p = annotation.hgvs_p
    if hgvs_c and ":c." in hgvs_c and not hgvs_c.startswith("NM_"):
        parts = hgvs_c.split(":")
        transcript = next((part for part in parts if part.startswith(("NM_", "ENST"))), None)
        cdna = next((part for part in parts if part.startswith("c.")), None)
        protein = next((part for part in parts if part.startswith("p.")), None)
        if transcript and cdna:
            hgvs_c = f"{transcript}:{cdna}"
        if not hgvs_p and protein:
            hgvs_p = protein
    elif hgvs_c and hgvs_c.startswith("c.") and annotation.transcript:
        hgvs_c = f"{annotation.transcript}:{hgvs_c}"
    return hgvs_c, hgvs_p


def _selected_annotation(
    annotations: list[VariantAnnotation],
    selected_transcript: str | None,
) -> VariantAnnotation:
    if selected_transcript:
        for annotation in annotations:
            if annotation.transcript == selected_transcript:
                return annotation
    return annotations[0]


def _record_options(
    base_options: dict[str, Any],
    annotations: list[VariantAnnotation],
    *,
    selected_transcript: str | None,
) -> dict[str, Any]:
    options = dict(base_options)
    options["include_transcript_selection"] = True
    options["annotations"] = [json.loads(annotation.model_dump_json()) for annotation in annotations]
    if selected_transcript:
        options["user_transcript"] = selected_transcript
    options.setdefault("mock_mode", True)
    return options


def _local_normalization_identity(record: dict[str, Any]) -> dict[str, Any] | None:
    payload = {key: value for key, value in record.items() if key not in {"options", "annotation_workflow"}}
    try:
        result = normalize_variant(payload)
    except NormalizationError as exc:
        return {
            "normalization_status": "unresolved",
            "unresolved_fields": exc.unresolved_fields,
            "limitations": [exc.message, *exc.warnings],
        }
    if result.variant_identity is None:
        return None
    return json.loads(result.variant_identity.model_dump_json())


def _context(arguments: dict[str, Any]) -> dict[str, Any] | None:
    context = arguments.get("gene_disease_context") or arguments.get("context")
    return dict(context) if isinstance(context, dict) else None


def _merge_annotation_failures(
    batch: dict[str, Any],
    annotation_failed: list[FailedBatchRecord],
) -> dict[str, Any]:
    if not annotation_failed:
        return batch
    failed_payloads = [json.loads(record.model_dump_json()) for record in annotation_failed]
    error_results = [
        {
            "input_index": record["input_index"],
            "input_record_hash": record["input_record_hash"],
            "normalized_variant_key": None,
            "status": "error",
            "classification_result": None,
            "error": record["error"],
            "review_required": True,
            "review_flags": [],
            "limitations": record["error"].get("limitations") or [],
            "annotation_provenance": [],
            "normalization_identity": None,
            "transcript_selection_summary": None,
        }
        for record in failed_payloads
    ]
    batch["results"] = sorted(
        [*batch.get("results", []), *error_results],
        key=lambda item: item["input_index"],
    )
    batch["failed_records"] = sorted(
        [*batch.get("failed_records", []), *failed_payloads],
        key=lambda item: item["input_index"],
    )
    batch["total_records"] = int(batch.get("total_records", 0)) + len(annotation_failed)
    batch["failed"] = int(batch.get("failed", 0)) + len(annotation_failed)
    return batch


def _malformed_annotation(index: int, raw: Any, message: str) -> FailedBatchRecord:
    raw_record = _jsonable(raw)
    return FailedBatchRecord(
        input_index=index,
        input_record_hash=_hash(raw_record),
        raw_record=raw_record if isinstance(raw_record, (dict, str)) else {"value": repr(raw_record)},
        error=BatchRecordError(
            code="MALFORMED_ANNOTATION_RECORD",
            message=message,
            details={},
            limitations=["Malformed annotation row captured; the batch continued."],
        ),
    )


def _pick(record: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        value = record.get(key)
        if value is None:
            value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _hash(value: Any) -> str:
    import hashlib

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _unique_dicts(values: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for value in values:
        marker = str(value.get(key) or value)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(value)
    return unique
