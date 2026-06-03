from __future__ import annotations

import argparse
import importlib
import importlib.metadata
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
from variant_pathogenicity_rater.pipeline.real_world import run_annotation_batch_workflow
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.normalization import NormalizationError, normalize_variant
from variant_pathogenicity_rater.variant_resolution import resolve_variant
from variant_pathogenicity_rater.literature_agent import create_reviewed_evidence_drafts
from variant_pathogenicity_rater.literature_agent import search_and_summarize_literature
from variant_pathogenicity_rater.natural_language_input import (
    rate_variant_from_text,
    render_clinical_context_review,
    render_parsed_input_review,
)
from variant_pathogenicity_rater.reporting import render_literature_search_summary_section
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
    rate.add_argument("--output", choices=["json", "markdown", "markdown-zh"], default="json")
    _add_report_arguments(rate)
    rate.add_argument("--reviewed-evidence", help="Reviewed evidence JSON file path.")
    rate.add_argument(
        "--include-clingen-erepo",
        action="store_true",
        help="Include ClinGen Evidence Repository review-note lookup.",
    )
    rate.add_argument(
        "--clingen-erepo-local-file",
        help="ClinGen ERepo local JSON/JSONL/CSV/TSV snapshot path.",
    )
    _add_population_arguments(rate)
    _add_vcep_arguments(rate)
    rate.set_defaults(handler=_cmd_rate)

    resolve = subparsers.add_parser(
        "resolve",
        help="Resolve descriptive transcript/protein/coordinate/exon/NMD context for a variant.",
    )
    _add_variant_arguments(resolve)
    resolve.add_argument("--hgvs", help="HGVS c. input such as NM_007294.4:c.68_69delAG.")
    resolve.add_argument("--output", choices=["json"], default="json")
    resolve.set_defaults(handler=_cmd_resolve)

    rate_text = subparsers.add_parser(
        "rate-text",
        help="Parse natural-language/HGVS text, then run the existing rate workflow.",
    )
    rate_text.add_argument("--text", required=True, help="Natural-language or HGVS variant text.")
    rate_text.add_argument("--output", choices=["json", "markdown", "markdown-zh"], default="json")
    _add_report_arguments(rate_text)
    rate_text.add_argument(
        "--include-clingen-erepo",
        action="store_true",
        help="Include ClinGen Evidence Repository review-note lookup.",
    )
    rate_text.add_argument(
        "--clingen-erepo-local-file",
        help="ClinGen ERepo local JSON/JSONL/CSV/TSV snapshot path.",
    )
    _add_population_arguments(rate_text)
    _add_vcep_arguments(rate_text)
    rate_text.add_argument(
        "--ai-assisted-context",
        action="store_true",
        help="Opt in to AI-assisted clinical-context candidate parsing when a provider is available.",
    )
    rate_text.add_argument(
        "--confirmed-context",
        help="Confirmed clinical context as JSON text or a JSON file path.",
    )
    rate_text.add_argument(
        "--no-require-context-confirmation",
        dest="require_context_confirmation",
        action="store_false",
        default=True,
        help="Do not require context confirmation when no AI candidate context is present.",
    )
    rate_text.set_defaults(handler=_cmd_rate_text)

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
    _add_report_arguments(batch)
    batch.add_argument("--reviewed-evidence", help="Reviewed evidence JSON file path.")
    batch.add_argument(
        "--include-clingen-erepo",
        action="store_true",
        help="Include ClinGen Evidence Repository review-note lookup for each record.",
    )
    batch.add_argument(
        "--clingen-erepo-local-file",
        help="ClinGen ERepo local JSON/JSONL/CSV/TSV snapshot path.",
    )
    _add_population_arguments(batch)
    _add_vcep_arguments(batch)
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
    _add_report_arguments(annotated)
    annotated.add_argument("--reviewed-evidence", help="Reviewed evidence JSON file path.")
    annotated.add_argument(
        "--include-report",
        action="store_true",
        help="Include per-record report text when available in the classification result.",
    )
    _add_population_arguments(annotated)
    annotated.set_defaults(handler=_cmd_annotated_batch)

    literature_draft = subparsers.add_parser(
        "literature-draft-reviewed",
        help="Convert literature suggested_evidence into manual reviewed_evidence draft templates.",
    )
    literature_draft.add_argument(
        "--literature-assessment-json",
        required=True,
        help="Path to assess_literature_evidence JSON output.",
    )
    literature_draft.add_argument(
        "--output",
        required=True,
        help="Output reviewed draft JSON path.",
    )
    literature_draft.set_defaults(handler=_cmd_literature_draft_reviewed)

    literature_search = subparsers.add_parser(
        "literature-search",
        help="Search and summarize literature records into candidate-only ACMG review suggestions.",
    )
    literature_search.add_argument("--gene", required=True)
    literature_search.add_argument("--variant", required=True)
    literature_search.add_argument("--transcript")
    literature_search.add_argument("--disease")
    literature_search.add_argument("--inheritance")
    literature_search.add_argument("--phenotype", action="append")
    literature_search.add_argument(
        "--criteria",
        action="append",
        help="Criterion or criterion group to summarize. May be repeated.",
    )
    literature_search.add_argument(
        "--literature-records",
        help="JSON file path or JSON text containing an array of literature records.",
    )
    literature_search.add_argument("--pmid", dest="pmids", action="append")
    literature_search.add_argument("--search-query")
    literature_search.add_argument("--variant-alias", dest="variant_aliases", action="append")
    literature_search.add_argument(
        "--online-pubmed",
        action="store_true",
        help="Opt in to PubMed online search. Local implementation records the opt-in and degrades safely.",
    )
    literature_search.add_argument(
        "--online-litvar",
        action="store_true",
        help="Opt in to LitVar online search. Local implementation records the opt-in and degrades safely.",
    )
    literature_search.add_argument("--output", help="Optional output file path.")
    literature_search.add_argument("--output-format", choices=["json", "markdown"], default="json")
    literature_search.set_defaults(handler=_cmd_literature_search)

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


def _add_vcep_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--include-vcep-signals",
        action="store_true",
        help="Include local VCEP profile signal lookup as review context.",
    )
    parser.add_argument(
        "--apply-vcep-overrides",
        action="store_true",
        help="Apply approved, explicit, limited VCEP profile generator overrides.",
    )
    parser.add_argument(
        "--vcep-profile-file",
        help="Local VCEP profile JSON or JSONL file.",
    )
    parser.add_argument(
        "--vcep-kb-dir",
        help="Local VCEP knowledge base directory containing disease_profiles/rule_overrides/vcep_signals.",
    )


def _add_population_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--population-local-file",
        help="Local gnomAD-like population JSON/JSONL/TSV snapshot path.",
    )
    parser.add_argument(
        "--population-source-version",
        default="cli-local-population-snapshot",
        help="Source version label for --population-local-file.",
    )


def _add_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--language",
        choices=["en", "zh"],
        default="en",
        help="Report language for generated report text. Defaults to en.",
    )
    parser.add_argument(
        "--report-mode",
        choices=["concise", "detailed", "laboratory", "clinician"],
        help="Report rendering mode. Defaults to detailed, or laboratory for markdown-zh.",
    )


def _cmd_rate(args: argparse.Namespace) -> int:
    payload = _variant_payload_from_args(args)
    if args.reviewed_evidence:
        payload["reviewed_evidence"] = _single_reviewed_evidence_payload(args.reviewed_evidence)
    payload["options"] = _clingen_erepo_options(args)
    result = rate_variant(payload)
    if args.output in {"markdown", "markdown-zh"}:
        print(str(result.get("report_text") or ""))
    else:
        print(_json_dumps(result))
    if result.get("status") != "ok":
        print(str(result.get("report_text") or "rate_variant failed"), file=sys.stderr)
        return 1
    return 0


def _cmd_rate_text(args: argparse.Namespace) -> int:
    options = _clingen_erepo_options(args)
    if getattr(args, "ai_assisted_context", False):
        options["ai_assisted_context"] = True
    options["require_context_confirmation"] = getattr(args, "require_context_confirmation", True)
    if getattr(args, "confirmed_context", None):
        options["confirmed_context"] = _load_json_argument(
            args.confirmed_context,
            label="confirmed context",
        )
    result = rate_variant_from_text(
        args.text,
        output=args.output,
        language=args.language,
        report_mode=args.report_mode,
        options=options,
    )
    if args.output in {"markdown", "markdown-zh"}:
        print(render_parsed_input_review(result))
        print()
        print(render_clinical_context_review(result))
        print()
        rate_result = result.get("rate_variant_result") if isinstance(result, dict) else None
        report_text = (rate_result or {}).get("report_text")
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        error_message = error.get("message")
        print(str(report_text or error_message or ""))
    else:
        print(_json_dumps(result))
    if result.get("status") != "ok":
        message = result.get("error", {}).get("message") or "rate_variant_from_text failed"
        print(str(message), file=sys.stderr)
        return 1
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
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
        }.items()
        if value is not None
    }
    if args.hgvs and "hgvs_c" not in payload:
        payload["hgvs_c"] = args.hgvs
    if not payload:
        raise CliError("resolve requires at least one variant field.", exit_code=2)
    try:
        normalization = normalize_variant(payload)
    except NormalizationError as exc:
        raise CliError(exc.message, exit_code=1) from exc
    if normalization.normalized_variant is None:
        raise CliError("resolve requires a normalizable SNV/small-indel variant.", exit_code=1)
    result = resolve_variant(normalization.normalized_variant)
    print(
        _json_dumps(
            {
                "status": result.status,
                "tool": "resolve_variant",
                "stage": "variant_resolution",
                "normalized_variant": (
                    normalization.normalized_variant.model_dump(mode="json")
                ),
                "resolved_variant": (
                    result.resolved_variant.model_dump(mode="json")
                    if result.resolved_variant is not None
                    else None
                ),
                "variant_resolution": result.model_dump(mode="json"),
                "human_review_required": True,
            }
        )
    )
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    input_text = _read_text(Path(args.input))
    payload = {
        "input_format": _batch_format(args.format),
        "input_text": input_text,
        "options": _clingen_erepo_options(args),
    }
    if args.reviewed_evidence:
        payload["reviewed_evidence"] = _load_json_file(args.reviewed_evidence)
    result = rate_variant_batch(payload)
    _add_chinese_batch_summary_if_requested(result, args)
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
    batch_result = run_annotation_batch_workflow(
        {
            "annotation_format": args.source,
            "input_text": input_text,
            "source_version": "cli-input",
            "options": _clingen_erepo_options(args),
            **(
                {"reviewed_evidence": _load_json_file(args.reviewed_evidence)}
                if args.reviewed_evidence
                else {}
            ),
        }
    )
    if args.include_report:
        _include_report_text(batch_result)
    converted = batch_result.get("annotation_to_batch_records") or {}
    parsed_count = int(converted.get("total_annotation_rows") or batch_result.get("total_records") or 0) - int(
        converted.get("failed_count") or 0
    )
    result = {
        "status": "ok",
        "tool": "annotated_batch",
        "annotation_source": args.source,
        "annotation_parse": {
            "parsed": parsed_count,
            "limitations": [
                limitation
                for limitation in batch_result.get("limitations", [])
                if "annotation" in str(limitation).lower()
            ],
        },
        "annotation_safety": {
            "review_flags": converted.get("review_flags") or [],
            "limitations": converted.get("limitations") or [],
        },
        "summary": {
            "total_records": batch_result.get("total_records", 0),
            "succeeded": batch_result.get("succeeded", 0),
            "failed": batch_result.get("failed", 0),
            "batch_summary": batch_result.get("summary", {}),
        },
        "batch": batch_result,
        "limitations": _unique(
            [
                *list(batch_result.get("limitations") or []),
                "Annotation workflow is descriptive only and does not directly generate ACMG evidence.",
            ]
        ),
        "human_review_required": True,
    }
    _add_chinese_batch_summary_if_requested(result, args)
    _write_result(result, args.output, args.output_format)
    if batch_result.get("failed", 0):
        print(
            "vpr annotated-batch: "
            f"{batch_result.get('failed')} of {batch_result.get('total_records')} records failed",
            file=sys.stderr,
        )
    return 0


def _cmd_literature_draft_reviewed(args: argparse.Namespace) -> int:
    assessment = _load_json_file(
        args.literature_assessment_json,
        label="literature assessment JSON",
    )
    result = create_reviewed_evidence_drafts(assessment)
    _write_result(result, args.output, "json")
    if result.get("status") != "ok":
        return 1
    return 0


def _cmd_literature_search(args: argparse.Namespace) -> int:
    records = []
    if args.literature_records:
        records_payload = _load_json_argument(args.literature_records, label="literature records")
        if not isinstance(records_payload, list):
            raise CliError("literature records must be a JSON array.", exit_code=2)
        records = records_payload
    result = search_and_summarize_literature(
        {
            "gene": args.gene,
            "variant": args.variant,
            "transcript": args.transcript,
            "disease": args.disease,
            "inheritance": args.inheritance,
            "phenotype": args.phenotype,
            "criteria": args.criteria or [],
            "literature_records": records,
            "pmids": args.pmids or [],
            "search_query": args.search_query,
            "variant_aliases": args.variant_aliases or [],
            "use_online_pubmed": bool(args.online_pubmed),
            "use_online_litvar": bool(args.online_litvar),
        }
    )
    dumped = json.loads(result.model_dump_json())
    if args.output_format == "markdown":
        text = render_literature_search_summary_section(dumped)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0
    _write_result(dumped, args.output, "json")
    return 0


def _cmd_check_env(_args: argparse.Namespace) -> int:
    mcp_server = Path(__file__).resolve().parents[2] / "mcp-server"
    if mcp_server.exists() and str(mcp_server) not in sys.path:
        sys.path.insert(0, str(mcp_server))

    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    print("Package import status:")
    for import_name, distribution_name in [
        ("pydantic", "pydantic"),
        ("pytest", "pytest"),
        ("variant_pathogenicity_rater", "variant-pathogenicity-rater-mcp"),
        ("server", None),
        ("tools", None),
    ]:
        print(f"  {import_name}: {_package_status(import_name, distribution_name)}")

    pytest_status = _package_status("pytest", "pytest")
    print(f"pytest availability: {pytest_status}")

    project_status = _package_status(
        "variant_pathogenicity_rater",
        "variant-pathogenicity-rater-mcp",
    )
    print(f"project import status: {project_status}")

    return 0


def _clingen_erepo_options(args: argparse.Namespace) -> dict[str, Any]:
    options: dict[str, Any] = {"mock_mode": True}
    data_source_overrides: dict[str, Any] = {}
    if getattr(args, "include_clingen_erepo", False) or getattr(args, "clingen_erepo_local_file", None):
        options["include_clingen_erepo"] = True
    local_file = getattr(args, "clingen_erepo_local_file", None)
    if local_file:
        data_source_overrides["clingen_erepo"] = {
            "mode": "local_file",
            "local_file": local_file,
            "source_version": "cli-local-clingen-erepo",
        }
    population_file = getattr(args, "population_local_file", None)
    if population_file:
        data_source_overrides["population"] = {
            "mode": "local_file",
            "local_file": population_file,
            "source_version": getattr(args, "population_source_version", None)
            or "cli-local-population-snapshot",
            "parser_version": "population-parser-v1",
        }
    if getattr(args, "include_vcep_signals", False):
        options["include_vcep_signals"] = True
    if getattr(args, "apply_vcep_overrides", False):
        options["include_vcep_signals"] = True
        options["apply_vcep_overrides"] = True
    if getattr(args, "vcep_profile_file", None):
        options["include_vcep_signals"] = True
        options["vcep_profile_file"] = args.vcep_profile_file
    if getattr(args, "vcep_kb_dir", None):
        options["include_vcep_signals"] = True
        options["vcep_kb_dir"] = args.vcep_kb_dir
    output = getattr(args, "output", None)
    language = getattr(args, "language", "en")
    report_mode = getattr(args, "report_mode", None)
    if output == "markdown-zh":
        language = "zh"
        report_mode = report_mode or "laboratory"
    if language == "zh":
        report_mode = report_mode or "laboratory"
    if language:
        options["report_language"] = language
    if report_mode:
        options["report_mode"] = report_mode
    if data_source_overrides:
        options["data_sources"] = {"sources": data_source_overrides}
    return options


def _add_chinese_batch_summary_if_requested(result: dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "language", "en") != "zh":
        return
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    result["summary_zh"] = {
        "用途": "批量结果摘要仅用于分诊和审计，不替代单条变异人工复核。",
        "总记录数": result.get("total_records") or summary.get("total_records") or 0,
        "成功": result.get("succeeded") or summary.get("succeeded") or 0,
        "失败": result.get("failed") or summary.get("failed") or 0,
        "人工复核必需": True,
        "说明": "中文 batch summary 不改变每条记录的分类、证据、局限性或人工复核要求。",
    }


def _package_status(import_name: str, distribution_name: str | None = None) -> str:
    distribution_name = distribution_name or import_name
    try:
        importlib.import_module(import_name)
    except Exception as exc:  # pragma: no cover - diagnostic output only
        return f"missing ({exc.__class__.__name__}: {exc})"

    try:
        version = importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        version = "installed, version unknown"
    return f"ok ({version})"


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


def _load_json_file(path_value: str, *, label: str = "reviewed evidence file") -> Any:
    path = Path(path_value)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"cannot read {label} {path}: {exc}", exit_code=2) from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"{label} is not valid JSON: {exc}", exit_code=2) from exc


def _load_json_argument(value: str, *, label: str) -> Any:
    path = Path(value)
    if path.exists():
        return _load_json_file(value, label=label)
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise CliError(f"{label} is neither a JSON file path nor valid JSON: {exc}", exit_code=2) from exc


def _single_reviewed_evidence_payload(path_value: str) -> Any:
    payload = _load_json_file(path_value)
    if isinstance(payload, dict) and "records" in payload:
        raise CliError(
            "single-variant --reviewed-evidence expects an array or an object with reviewed_evidence.",
            exit_code=2,
        )
    return payload.get("reviewed_evidence") if isinstance(payload, dict) else payload


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
