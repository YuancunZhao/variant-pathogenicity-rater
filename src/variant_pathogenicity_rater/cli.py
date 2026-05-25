from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from variant_pathogenicity_rater.annotation import (
    AnnovarAdapter,
    BcftoolsCsqAdapter,
    GenericTableAdapter,
    VepAdapter,
    evaluate_annotation_safety,
    select_transcript,
)
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.schemas.annotation import VariantAnnotation


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if not hasattr(args, "handler"):
        parser.print_help(sys.stderr)
        return 2
    try:
        return int(args.handler(args))
    except CliError as exc:
        print(f"vpr: error: {exc}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:  # pragma: no cover - depends on shell pipeline behavior.
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vpr",
        description="Variant Pathogenicity Rater command line interface.",
    )
    subparsers = parser.add_subparsers(dest="command")

    rate = subparsers.add_parser("rate", help="Rate a single SNV/small indel variant.")
    _add_variant_arguments(rate)
    rate.add_argument("--output", choices=["json", "markdown"], default="json")
    rate.set_defaults(handler=_cmd_rate)

    batch = subparsers.add_parser("batch", help="Rate a batch of variants.")
    batch.add_argument("--input", required=True, help="Input file path.")
    batch.add_argument(
        "--format",
        required=True,
        choices=["json", "jsonl", "csv", "tsv", "vcf-like"],
        help="Input format.",
    )
    batch.add_argument("--output", help="Optional output file path.")
    batch.add_argument("--output-format", choices=["json", "jsonl"], default="json")
    batch.add_argument(
        "--continue-on-error",
        dest="continue_on_error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue after per-record errors. Defaults to true.",
    )
    batch.set_defaults(handler=_cmd_batch)

    annotated = subparsers.add_parser(
        "annotated-batch",
        help="Rate variants from an annotation table without turning annotation into ACMG evidence.",
    )
    annotated.add_argument("--input", required=True, help="Annotation input file path.")
    annotated.add_argument(
        "--source",
        required=True,
        choices=["vep", "annovar", "bcftools", "generic"],
        help="Annotation source format.",
    )
    annotated.add_argument("--output", help="Optional output file path.")
    annotated.add_argument("--output-format", choices=["json", "jsonl"], default="json")
    annotated.add_argument(
        "--include-report",
        action="store_true",
        help="Include per-record report text when available in the classification result.",
    )
    annotated.set_defaults(handler=_cmd_annotated_batch)

    check_env = subparsers.add_parser("check-env", help="Print local environment diagnostics.")
    check_env.set_defaults(handler=_cmd_check_env)

    return parser


def _add_variant_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gene")
    parser.add_argument("--transcript")
    parser.add_argument("--hgvs-c", dest="hgvs_c")
    parser.add_argument("--hgvs-p", dest="hgvs_p")
    parser.add_argument("--chromosome")
    parser.add_argument("--position", type=int)
    parser.add_argument("--ref")
    parser.add_argument("--alt")
    parser.add_argument("--disease")
    parser.add_argument("--inheritance")


def _cmd_rate(args: argparse.Namespace) -> int:
    payload = _variant_payload_from_args(args)
    payload["options"] = {"mock_mode": True}
    result = rate_variant(payload)
    if args.output == "markdown":
        print(str(result.get("report_text") or ""))
    else:
        print(_json_dumps(result))
    if result.get("status") != "ok":
        print(str(result.get("report_text") or "rate_variant failed"), file=sys.stderr)
        return 1
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    input_text = _read_text(Path(args.input))
    result = rate_variant_batch(
        {
            "input_format": _batch_format(args.format),
            "input_text": input_text,
            "options": {"mock_mode": True},
        }
    )
    _write_result(result, args.output, args.output_format)
    if result.get("failed", 0):
        print(
            f"vpr batch: {result.get('failed')} of {result.get('total_records')} records failed",
            file=sys.stderr,
        )
    if result.get("failed", 0) and not args.continue_on_error:
        return 1
    return 0


def _cmd_annotated_batch(args: argparse.Namespace) -> int:
    input_text = _read_text(Path(args.input))
    adapter = _annotation_adapter(args.source)
    parse_result = adapter.parse_text(input_text)
    safety = evaluate_annotation_safety(parse_result.annotations)
    records = _records_from_annotations(parse_result.annotations)
    batch_result = rate_variant_batch({"records": records, "options": {"mock_mode": True}})
    if args.include_report:
        _include_report_text(batch_result)
    result = {
        "status": "ok",
        "tool": "annotated_batch",
        "annotation_source": args.source,
        "annotation_parse": {
            "parsed": len(parse_result.annotations),
            "limitations": parse_result.limitations,
        },
        "annotation_safety": {
            "review_flags": [json.loads(flag.model_dump_json()) for flag in safety.review_flags],
            "limitations": safety.limitations,
        },
        "summary": {
            "total_records": batch_result.get("total_records", 0),
            "succeeded": batch_result.get("succeeded", 0),
            "failed": batch_result.get("failed", 0),
        },
        "batch": batch_result,
        "limitations": _unique(
            [
                *parse_result.limitations,
                *safety.limitations,
                "Annotation workflow is descriptive only and does not directly generate ACMG evidence.",
            ]
        ),
        "human_review_required": True,
    }
    _write_result(result, args.output, args.output_format)
    if batch_result.get("failed", 0):
        print(
            "vpr annotated-batch: "
            f"{batch_result.get('failed')} of {batch_result.get('total_records')} records failed",
            file=sys.stderr,
        )
    return 0


def _cmd_check_env(_args: argparse.Namespace) -> int:
    try:
        from scripts.check_env import main as check_env_main
    except Exception:
        from importlib import import_module

        check_env_main = import_module("check_env").main
    return int(check_env_main())


def _variant_payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in {
            "gene": args.gene,
            "transcript": args.transcript,
            "hgvs_c": args.hgvs_c,
            "hgvs_p": args.hgvs_p,
            "chromosome": args.chromosome,
            "position": args.position,
            "ref": args.ref,
            "alt": args.alt,
            "disease": args.disease,
            "inheritance": args.inheritance,
        }.items()
        if value is not None
    }
    if not payload:
        raise CliError("rate requires at least one variant field.", exit_code=2)
    return payload


def _annotation_adapter(source: str) -> Any:
    if source == "vep":
        return VepAdapter(source_version="cli-input")
    if source == "annovar":
        return AnnovarAdapter(source_version="cli-input")
    if source == "bcftools":
        return BcftoolsCsqAdapter(source_version="cli-input")
    if source == "generic":
        return GenericTableAdapter(source_version="cli-input")
    raise CliError(f"unsupported annotation source: {source}", exit_code=2)


def _records_from_annotations(annotations: list[VariantAnnotation]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    selection = select_transcript(annotations)
    selection_summary = json.loads(selection.model_dump_json())
    provenance = [
        json.loads(annotation.provenance.model_dump_json())
        for annotation in annotations
        if annotation.provenance is not None
    ]
    for index, annotation in enumerate(annotations):
        raw = annotation.raw_fields
        record = {
            "_annotation_input_index": index,
            "gene": annotation.gene,
            "transcript": annotation.transcript,
            "hgvs_c": annotation.hgvs_c,
            "hgvs_p": annotation.hgvs_p,
            "chromosome": _first(raw, "#CHROM", "CHROM", "Chr", "chrom", "chromosome"),
            "position": _int_or_none(_first(raw, "POS", "Start", "pos", "position")),
            "ref": _first(raw, "REF", "Ref", "ref"),
            "alt": _first(raw, "ALT", "Alt", "alt"),
            "disease": _first(raw, "disease", "Disease") or "not provided",
            "inheritance": _first(raw, "inheritance", "Inheritance"),
            "annotation_workflow": {
                "annotation_source": annotation.annotation_source,
                "annotation_provenance": provenance,
                "transcript_selection_summary": selection_summary,
                "annotation_is_acmg_evidence": False,
            },
            "options": {
                "mock_mode": True,
                "include_transcript_selection": True,
                "annotations": [json.loads(annotation.model_dump_json())],
                "user_transcript": annotation.transcript,
            },
        }
        parsed_uploaded = _parse_uploaded_variation(_first(raw, "Uploaded_variation"))
        for key, value in parsed_uploaded.items():
            if record.get(key) is None:
                record[key] = value
        records.append({key: value for key, value in record.items() if value is not None})
    return records


def _parse_uploaded_variation(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    # Handles common VEP examples such as 1_123_A/G.
    parts = value.split("_")
    if len(parts) != 3 or "/" not in parts[2]:
        return {}
    ref, alt = parts[2].split("/", 1)
    return {
        "chromosome": parts[0],
        "position": _int_or_none(parts[1]),
        "ref": ref,
        "alt": alt,
    }


def _include_report_text(result: dict[str, Any]) -> None:
    for item in result.get("results", []):
        classification = item.get("classification_result")
        if isinstance(classification, dict) and classification.get("report_text"):
            item["report_text"] = classification["report_text"]


def _write_result(result: dict[str, Any], output_path: str | None, output_format: str) -> None:
    text = _format_output(result, output_format)
    if output_path:
        Path(output_path).write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    else:
        print(text)


def _format_output(result: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return _json_dumps(result)
    if output_format == "jsonl":
        if "batch" in result and isinstance(result["batch"], dict):
            lines = _batch_jsonl_lines(result["batch"])
            lines.append(_json_line({"type": "annotated_summary", "summary": result["summary"]}))
            return "\n".join(lines)
        return "\n".join(_batch_jsonl_lines(result))
    raise CliError(f"unsupported output format: {output_format}", exit_code=2)


def _batch_jsonl_lines(result: dict[str, Any]) -> list[str]:
    lines = [_json_line({"type": "result", "record": item}) for item in result.get("results", [])]
    lines.append(
        _json_line(
            {
                "type": "summary",
                "batch_id": result.get("batch_id"),
                "total_records": result.get("total_records", 0),
                "succeeded": result.get("succeeded", 0),
                "failed": result.get("failed", 0),
                "warnings": result.get("warnings", []),
            }
        )
    )
    return lines


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"cannot read input file {path}: {exc}", exit_code=2) from exc


def _batch_format(value: str) -> str:
    return "vcf_like" if value == "vcf-like" else value


def _first(record: dict[str, Any], *keys: str) -> str | None:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        value = record.get(key)
        if value is None:
            value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value)
    return None


def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _json_line(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


class CliError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
