from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.schemas.batch import (
    BatchRecordError,
    BatchResult,
    BatchVariantResult,
    FailedBatchRecord,
)

SUPPORTED_BATCH_FORMATS = {"json", "jsonl", "csv", "tsv", "vcf", "vcf_like"}
VARIANT_FIELDS = {
    "gene",
    "gene_symbol",
    "transcript",
    "hgvs_c",
    "hgvs_p",
    "chromosome",
    "chrom",
    "position",
    "pos",
    "ref",
    "alt",
    "disease",
    "inheritance",
    "phenotype",
    "phenotype_terms",
    "options",
    "variant",
    "gene_disease_context",
    "context",
}


@dataclass(frozen=True)
class ParsedRecord:
    input_index: int
    record: dict[str, Any]


@dataclass(frozen=True)
class ParsedBatch:
    records: list[ParsedRecord]
    failed_records: list[FailedBatchRecord]
    warnings: list[str]
    total_records: int


def rate_variant_batch(arguments: dict[str, Any]) -> dict[str, Any]:
    started_at = _timestamp()
    batch_id = str(arguments.get("batch_id") or f"batch-{uuid.uuid4()}")
    parsed = parse_batch(arguments)
    results: list[BatchVariantResult] = []
    failed_records = list(parsed.failed_records)
    warnings = list(parsed.warnings)
    limitations = [
        "Batch mode calls the existing rate_variant pipeline per record and does not change ACMG classification logic.",
        "Mock mode is enabled by default; no network access was attempted unless explicitly configured per record.",
        "Batch output is a triage aid only and cannot replace qualified human review.",
    ]

    for failed in parsed.failed_records:
        results.append(
            BatchVariantResult(
                input_index=failed.input_index,
                input_record_hash=failed.input_record_hash,
                normalized_variant_key=None,
                status="error",
                error=failed.error,
                review_required=True,
                limitations=failed.error.limitations,
            )
        )

    seen_keys: dict[str, int] = {}
    for parsed_record in parsed.records:
        output_index = _record_output_index(parsed_record)
        preflight_error = _preflight_error(parsed_record.record)
        if preflight_error is not None:
            failed = FailedBatchRecord(
                input_index=output_index,
                input_record_hash=_record_hash(parsed_record.record),
                raw_record=parsed_record.record,
                error=preflight_error,
            )
            failed_records.append(failed)
            results.append(_failed_result(failed))
            continue

        record = _with_default_options(parsed_record.record, arguments.get("options"))
        try:
            pipeline_result = rate_variant(record)
        except Exception as exc:  # noqa: BLE001 - one failed record must not fail the batch.
            error = BatchRecordError(
                code="RATE_VARIANT_EXCEPTION",
                message=f"rate_variant failed for this record: {exc.__class__.__name__}: {exc}",
                details={"exception_type": exc.__class__.__name__},
                limitations=["This record failed independently; the batch continued."],
            )
            failed = FailedBatchRecord(
                input_index=output_index,
                input_record_hash=_record_hash(parsed_record.record),
                raw_record=parsed_record.record,
                error=error,
            )
            failed_records.append(failed)
            results.append(_failed_result(failed))
            continue

        if pipeline_result.get("status") != "ok":
            error = BatchRecordError(
                code=str(pipeline_result.get("stage") or "RATE_VARIANT_ERROR"),
                message=str(pipeline_result.get("report_text") or "rate_variant returned an error."),
                details={"pipeline_status": pipeline_result.get("status")},
                limitations=list(pipeline_result.get("limitations") or []),
            )
            failed = FailedBatchRecord(
                input_index=output_index,
                input_record_hash=_record_hash(parsed_record.record),
                raw_record=parsed_record.record,
                error=error,
            )
            failed_records.append(failed)
            results.append(_failed_result(failed))
            continue

        normalized_key = _normalized_key(pipeline_result)
        if normalized_key:
            if normalized_key in seen_keys:
                warnings.append(
                    "Duplicate variant detected: "
                    f"record {output_index} duplicates record {seen_keys[normalized_key]} "
                    f"({normalized_key})."
                )
            else:
                seen_keys[normalized_key] = output_index

        classification_result = pipeline_result.get("classification_result")
        review_flags = []
        if isinstance(classification_result, dict):
            review_flags = list(classification_result.get("review_flags") or [])
        results.append(
            BatchVariantResult(
                input_index=output_index,
                input_record_hash=_record_hash(parsed_record.record),
                normalized_variant_key=normalized_key,
                status="ok",
                classification_result=classification_result,
                review_required=bool(pipeline_result.get("human_review_required", True)),
                review_flags=review_flags,
                limitations=list(pipeline_result.get("limitations") or []),
                annotation_provenance=_annotation_provenance(parsed_record.record),
                normalization_identity=_normalization_identity(pipeline_result),
                transcript_selection_summary=_transcript_selection_summary(
                    pipeline_result,
                    parsed_record.record,
                ),
            )
        )

    succeeded = sum(1 for result in results if result.status == "ok")
    failed = sum(1 for result in results if result.status == "error")
    batch = BatchResult(
        batch_id=batch_id,
        total_records=parsed.total_records,
        succeeded=succeeded,
        failed=failed,
        results=sorted(results, key=lambda item: item.input_index),
        failed_records=sorted(failed_records, key=lambda item: item.input_index),
        warnings=_unique(warnings),
        limitations=_unique(limitations),
        started_at=started_at,
        completed_at=_timestamp(),
    )
    return json.loads(batch.model_dump_json())


def parse_batch(arguments: dict[str, Any]) -> ParsedBatch:
    if isinstance(arguments.get("records"), list):
        return _parse_records(arguments["records"])
    if "input_text" in arguments:
        input_text = arguments.get("input_text")
    elif "text" in arguments:
        input_text = arguments.get("text")
    elif "data" in arguments:
        input_text = arguments.get("data")
    else:
        raise ValueError("Batch input requires 'records' or textual 'input_text'.")
    if not isinstance(input_text, str):
        raise ValueError("Batch textual input must be a string.")
    input_format = str(arguments.get("input_format") or arguments.get("format") or "json").lower()
    if input_format not in SUPPORTED_BATCH_FORMATS:
        raise ValueError(f"Unsupported batch input format: {input_format}")
    if input_format == "json":
        return _parse_json_array(input_text)
    if input_format == "jsonl":
        return _parse_jsonl(input_text)
    if input_format == "csv":
        return _parse_delimited(input_text, delimiter=",", vcf_like=False)
    if input_format in {"tsv", "vcf", "vcf_like"}:
        return _parse_delimited(input_text, delimiter="\t", vcf_like=input_format != "tsv")
    raise ValueError(f"Unsupported batch input format: {input_format}")


def _parse_records(records: list[Any]) -> ParsedBatch:
    parsed: list[ParsedRecord] = []
    failed: list[FailedBatchRecord] = []
    for index, record in enumerate(records):
        if isinstance(record, dict):
            try:
                parsed.append(ParsedRecord(index, _normalize_record(record)))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                failed.append(_malformed(index, record, f"Record normalization failed: {exc}"))
        else:
            failed.append(_malformed(index, record, "Batch JSON array items must be objects."))
    return ParsedBatch(parsed, failed, [], len(records))


def _parse_json_array(text: str) -> ParsedBatch:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        failed = [_malformed(0, text, f"JSON parse failed: {exc}")]
        return ParsedBatch([], failed, [], 1)
    if not isinstance(data, list):
        failed = [_malformed(0, data, "JSON batch input must be an array.")]
        return ParsedBatch([], failed, [], 1)
    return _parse_records(data)


def _parse_jsonl(text: str) -> ParsedBatch:
    parsed: list[ParsedRecord] = []
    failed: list[FailedBatchRecord] = []
    index = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            failed.append(_malformed(index, line, f"JSONL line {line_number} parse failed: {exc}"))
            index += 1
            continue
        if isinstance(record, dict):
            parsed.append(ParsedRecord(index, _normalize_record(record)))
        else:
            failed.append(_malformed(index, line, f"JSONL line {line_number} must be an object."))
        index += 1
    return ParsedBatch(parsed, failed, [], index)


def _parse_delimited(text: str, *, delimiter: str, vcf_like: bool) -> ParsedBatch:
    rows = [line for line in text.splitlines() if line.strip() and not line.startswith("##")]
    if not rows:
        return ParsedBatch([], [], ["Batch input contained no records."], 0)
    reader = csv.DictReader(io.StringIO("\n".join(rows)), delimiter=delimiter)
    parsed: list[ParsedRecord] = []
    failed: list[FailedBatchRecord] = []
    for index, row in enumerate(reader):
        if None in row:
            failed.append(_malformed(index, row, "Delimited row has more fields than the header."))
            continue
        cleaned = {str(key).strip(): value for key, value in row.items() if key is not None}
        if not any(value not in (None, "") for value in cleaned.values()):
            failed.append(_malformed(index, cleaned, "Delimited row is empty."))
            continue
        try:
            record = _normalize_vcf_record(cleaned) if vcf_like else _normalize_record(cleaned)
        except ValueError as exc:
            failed.append(_malformed(index, cleaned, str(exc)))
            continue
        parsed.append(ParsedRecord(index, record))
    return ParsedBatch(parsed, failed, [], len(parsed) + len(failed))


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        if value == "":
            continue
        mapped = _map_field_name(str(key))
        normalized[mapped] = _coerce_value(mapped, value)
    return normalized


def _normalize_vcf_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_record(record)
    for source, target in {
        "#CHROM": "chromosome",
        "CHROM": "chromosome",
        "POS": "position",
        "REF": "ref",
        "ALT": "alt",
    }.items():
        if source in record and target not in normalized and record[source] != "":
            normalized[target] = _coerce_value(target, record[source])
    if "alt" in normalized and isinstance(normalized["alt"], str) and "," in normalized["alt"]:
        raise ValueError("Multi-allelic VCF rows are not split silently; submit one ALT per record.")
    return normalized


def _map_field_name(key: str) -> str:
    cleaned = key.strip()
    upper = cleaned.upper()
    aliases = {
        "#CHROM": "chromosome",
        "CHROM": "chromosome",
        "POS": "position",
        "REF": "ref",
        "ALT": "alt",
        "GENE": "gene",
        "GENE_SYMBOL": "gene",
        "TRANSCRIPT": "transcript",
        "HGVS_C": "hgvs_c",
        "HGVS_P": "hgvs_p",
        "DISEASE": "disease",
        "INHERITANCE": "inheritance",
        "PHENOTYPE": "phenotype",
    }
    return aliases.get(upper, cleaned)


def _coerce_value(field: str, value: Any) -> Any:
    if field in {"position", "pos"} and isinstance(value, str):
        return int(value)
    if field in {"phenotype", "phenotype_terms"} and isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    if field == "options" and isinstance(value, str):
        return json.loads(value)
    return value


def _with_default_options(record: dict[str, Any], batch_options: Any) -> dict[str, Any]:
    payload = dict(record)
    options: dict[str, Any] = {}
    if isinstance(batch_options, dict):
        options.update(batch_options)
    if isinstance(payload.get("options"), dict):
        options.update(payload["options"])
    options.setdefault("mock_mode", True)
    payload["options"] = options
    return payload


def _preflight_error(record: dict[str, Any]) -> BatchRecordError | None:
    unsupported_type = str(record.get("variant_type") or record.get("type") or "").lower()
    if unsupported_type in {"cnv", "sv", "structural_variant", "repeat", "str", "repeat_expansion"}:
        return BatchRecordError(
            code="UNSUPPORTED_VARIANT_TYPE",
            message="Batch mode supports SNV/small indel records only; CNV/SV/repeat input is unsupported.",
            details={"variant_type": unsupported_type},
            limitations=["Unsupported variant captured for per-record review; no ACMG rating was attempted."],
        )
    alt = record.get("alt")
    if isinstance(alt, list) and len(alt) != 1:
        return BatchRecordError(
            code="UNSUPPORTED_MULTIALLELIC",
            message="Multi-allelic input is not split or interpreted silently.",
            details={"alt": alt},
            limitations=["Submit one alternate allele per record."],
        )
    if isinstance(alt, str) and ("," in alt or alt.startswith("<") or alt.endswith(">")):
        return BatchRecordError(
            code="UNSUPPORTED_VARIANT_TYPE",
            message="Symbolic or multi-allelic ALT values are unsupported for SNV/small indel batch rating.",
            details={"alt": alt},
            limitations=["Unsupported VCF row captured; no silent interpretation was performed."],
        )
    ref = record.get("ref")
    if isinstance(ref, str) and ref.startswith("<"):
        return BatchRecordError(
            code="UNSUPPORTED_VARIANT_TYPE",
            message="Symbolic REF values are unsupported for SNV/small indel batch rating.",
            details={"ref": ref},
            limitations=["Unsupported VCF row captured; no silent interpretation was performed."],
        )
    return None


def _failed_result(failed: FailedBatchRecord) -> BatchVariantResult:
    return BatchVariantResult(
        input_index=failed.input_index,
        input_record_hash=failed.input_record_hash,
        normalized_variant_key=None,
        status="error",
        error=failed.error,
        review_required=True,
        limitations=failed.error.limitations,
    )


def _record_output_index(parsed_record: ParsedRecord) -> int:
    value = parsed_record.record.get("_annotation_input_index")
    if isinstance(value, int) and value >= 0:
        return value
    return parsed_record.input_index


def _malformed(index: int, raw: Any, message: str) -> FailedBatchRecord:
    error = BatchRecordError(
        code="MALFORMED_RECORD",
        message=message,
        details={},
        limitations=["Malformed record captured; the batch continued."],
    )
    raw_record: dict[str, Any] | str | None
    raw_record = raw if isinstance(raw, (dict, str)) else {"value": repr(raw)}
    return FailedBatchRecord(
        input_index=index,
        input_record_hash=_record_hash(raw),
        raw_record=raw_record,
        error=error,
    )


def _normalized_key(pipeline_result: dict[str, Any]) -> str | None:
    identity = (pipeline_result.get("step_results") or {}).get("normalize_variant", {}).get(
        "variant_identity"
    )
    if isinstance(identity, dict):
        key = identity.get("normalized_variant_key")
        if key:
            return str(key)
    variant = pipeline_result.get("normalized_variant")
    if isinstance(variant, dict):
        chrom = variant.get("chrom")
        pos = variant.get("pos")
        ref = variant.get("ref")
        alt = variant.get("alt")
        if chrom and pos and ref and alt:
            return f"{chrom}-{pos}-{ref}-{alt}"
    return None


def _normalization_identity(pipeline_result: dict[str, Any]) -> dict[str, Any] | None:
    identity = (pipeline_result.get("step_results") or {}).get("normalize_variant", {}).get(
        "variant_identity"
    )
    return identity if isinstance(identity, dict) else None


def _transcript_selection_summary(
    pipeline_result: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any] | None:
    workflow = record.get("annotation_workflow")
    if isinstance(workflow, dict) and isinstance(
        workflow.get("transcript_selection_summary"), dict
    ):
        selection = workflow["transcript_selection_summary"]
        return {
            "selected_transcript": selection.get("selected_transcript"),
            "selected_gene": selection.get("selected_gene"),
            "selection_reason": selection.get("selection_reason"),
            "selection_confidence": selection.get("selection_confidence"),
            "candidate_transcripts": selection.get("candidate_transcripts") or [],
            "review_flags": selection.get("review_flags") or [],
            "limitations": selection.get("limitations") or [],
            "provenance": selection.get("provenance") or {},
        }
    selection = pipeline_result.get("transcript_selection") or (
        (pipeline_result.get("classification_result") or {}).get("transcript_selection")
        if isinstance(pipeline_result.get("classification_result"), dict)
        else None
    )
    if not isinstance(selection, dict):
        return None
    return {
        "selected_transcript": selection.get("selected_transcript"),
        "selected_gene": selection.get("selected_gene"),
        "selection_reason": selection.get("selection_reason"),
        "selection_confidence": selection.get("selection_confidence"),
        "candidate_transcripts": selection.get("candidate_transcripts") or [],
        "review_flags": selection.get("review_flags") or [],
        "limitations": selection.get("limitations") or [],
        "provenance": selection.get("provenance") or {},
    }


def _annotation_provenance(record: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = record.get("annotation_workflow")
    if not isinstance(workflow, dict):
        return []
    provenance = workflow.get("annotation_provenance")
    if isinstance(provenance, list):
        return [item for item in provenance if isinstance(item, dict)]
    return []


def _record_hash(record: Any) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
