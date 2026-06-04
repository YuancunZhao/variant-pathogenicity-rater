from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any


CANONICAL_OUTPUT_VERSION = "77A-output-schema-v1"

LEGACY_FIELD_REPLACEMENTS = {
    "mock_mode": "runtime.legacy_mock_mode",
    "offline_default_mode": "runtime.offline_default_mode",
    "data_source_modes": "runtime.data_source_modes_configured",
    "data_source_modes_semantics": "runtime.data_source_modes_semantics",
    "provider_mode_summary": "providers.summary",
    "unresolved_placeholder_mode": "runtime.unresolved_placeholder_mode",
    "normalized_variant": "variant.normalized",
    "resolved_variant": "variant.resolved",
    "variant_resolution": "variant.resolution_summary",
    "variant_resolution_summary": "variant.resolution_summary",
    "transcript_validation": "variant.transcript_validation",
    "evidence_items": "evidence.all_items",
    "applied_evidence": "evidence.applied",
    "candidate_evidence": "evidence.candidate",
    "review_note_evidence": "evidence.review_note",
    "reviewed_evidence": "evidence.reviewed",
    "classification_result": "classification.classification_result",
    "final_classification": "classification.final_classification",
    "human_review_required": "review.human_review_required",
    "human_review": "review.human_review_required",
    "review_flags": "review.review_flags",
    "limitations": "limitations",
    "report_text": "report.report_text",
    "report": "report",
    "step_results": "step_results",
}


def build_rate_variant_canonical_output(
    result: dict[str, Any],
    *,
    original_input: dict[str, Any] | None = None,
    parsed_input: dict[str, Any] | None = None,
    input_type: str | None = None,
    context_used_for_rating: str | None = None,
    confirmed_context: dict[str, Any] | None = None,
    context_candidates: list[Any] | None = None,
) -> dict[str, Any]:
    """Build additive canonical output views from an existing rate_variant result."""

    options_used = _options_used(original_input, parsed_input, result)
    canonical = {
        "version": CANONICAL_OUTPUT_VERSION,
        "input": {
            "original_input": _json_copy(original_input or {}),
            "parsed_input": _json_copy(parsed_input or {}),
            "input_type": input_type or _infer_input_type(original_input, parsed_input, result),
            "options_used": options_used,
        },
        "variant": _variant_section(result),
        "context": _context_section(
            result,
            original_input=original_input,
            parsed_input=parsed_input,
            context_used_for_rating=context_used_for_rating,
            confirmed_context=confirmed_context,
            context_candidates=context_candidates,
        ),
        "runtime": _runtime_section(result, options_used),
        "providers": _providers_section(result),
        "evidence": _evidence_section(result),
        "classification": _classification_section(result),
        "review": _review_section(result),
        "report": _report_section(result, options_used),
        "provenance": _provenance_section(result, options_used),
        "warnings": _warnings(result),
        "compatibility": _compatibility_section(result),
    }
    return canonical


def add_rate_variant_canonical_fields(
    result: dict[str, Any],
    *,
    original_input: dict[str, Any] | None = None,
    parsed_input: dict[str, Any] | None = None,
    input_type: str | None = None,
    context_used_for_rating: str | None = None,
    confirmed_context: dict[str, Any] | None = None,
    context_candidates: list[Any] | None = None,
) -> dict[str, Any]:
    canonical = build_rate_variant_canonical_output(
        result,
        original_input=original_input,
        parsed_input=parsed_input,
        input_type=input_type,
        context_used_for_rating=context_used_for_rating,
        confirmed_context=confirmed_context,
        context_candidates=context_candidates,
    )
    result["version"] = canonical["version"]
    for key in (
        "input",
        "variant",
        "context",
        "runtime",
        "providers",
        "evidence",
        "classification",
        "review",
        "warnings",
        "compatibility",
    ):
        result[key] = canonical[key]
    result["candidate_evidence"] = _json_copy(result.get("candidate_evidence") or canonical["evidence"]["candidate"])
    result["report"] = _merge_report(result.get("report"), canonical["report"])
    result["provenance"] = _merge_provenance(result.get("provenance"), canonical["provenance"])
    return result


def add_text_canonical_fields(result: dict[str, Any]) -> dict[str, Any]:
    rate_result = result.get("rate_variant_result")
    parsed_input = _json_copy(result.get("parsed_input") or {})
    text_input = str(result.get("input_text") or "")
    original_input = {"text": text_input}
    if isinstance(rate_result, dict):
        canonical = build_rate_variant_canonical_output(
            rate_result,
            original_input=original_input,
            parsed_input=parsed_input,
            input_type="natural_language_text",
            context_used_for_rating=result.get("context_used_for_rating"),
            confirmed_context=_dict_or_none(result.get("confirmed_context")),
            context_candidates=list(result.get("context_candidates") or []),
        )
        for key in (
            "version",
            "variant",
            "runtime",
            "providers",
            "evidence",
            "classification",
            "report",
            "provenance",
            "compatibility",
        ):
            result[key] = canonical[key]
        result["review"] = {
            **canonical["review"],
            "review_questions": canonical["review"].get("review_questions") or [],
        }
    else:
        canonical = _empty_text_canonical(result, original_input, parsed_input)
        for key, value in canonical.items():
            result[key] = value
    result["input"] = {
        "original_input": original_input,
        "parsed_input": parsed_input,
        "input_type": "natural_language_text",
        "options_used": parsed_input.get("options") if isinstance(parsed_input.get("options"), dict) else {},
    }
    result["context"] = {
        **_context_section(
            rate_result if isinstance(rate_result, dict) else {},
            original_input=original_input,
            parsed_input=parsed_input,
            context_used_for_rating=result.get("context_used_for_rating"),
            confirmed_context=_dict_or_none(result.get("confirmed_context")),
            context_candidates=list(result.get("context_candidates") or []),
        ),
        "context_confirmation_required": result.get("context_confirmation_required"),
    }
    result["warnings"] = _unique(
        [
            *[str(item) for item in result.get("ambiguity_warnings") or []],
            *[str(item) for item in result.get("normalization_warnings") or []],
        ]
    )
    return result


def canonical_batch_record_summary(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant": _json_copy(pipeline_result.get("variant") or {}),
        "runtime": _json_copy(pipeline_result.get("runtime") or {}),
        "providers": _json_copy(pipeline_result.get("providers") or {}),
        "evidence": _json_copy(pipeline_result.get("evidence") or {}),
        "classification": _json_copy(pipeline_result.get("classification") or {}),
        "review": _json_copy(pipeline_result.get("review") or {}),
    }


def failed_batch_record_canonical_summary(error: Any) -> dict[str, Any]:
    limitations = list(getattr(error, "limitations", None) or [])
    return {
        "variant": {
            "normalized": None,
            "resolved": None,
            "resolution_summary": None,
            "transcript_validation": None,
            "unresolved_fields": [],
            "placeholder_fields": [],
        },
        "runtime": {
            "legacy_mock_mode": True,
            "offline_default_mode": True,
            "data_source_modes_configured": {},
            "data_source_modes_semantics": "",
            "unresolved_placeholder_mode": True,
            "network_policy": {"default_network_enabled": False, "online_requested": False},
            "cache_policy": {"cache_dir": None, "cache_enabled": False},
        },
        "providers": _providers_section({}),
        "evidence": {
            "applied": [],
            "candidate": [],
            "review_note": [],
            "reviewed": [],
            "all_items": [],
            "evidence_status_summary": _evidence_status_summary([], []),
        },
        "classification": {
            "final_classification": None,
            "applied_combination_rule": None,
            "confidence": None,
            "classification_result": None,
            "classification_changed_by_reviewed_evidence": False,
        },
        "review": {
            "human_review_required": True,
            "review_flags": [],
            "review_questions": [],
            "blocking_reasons": limitations,
        },
    }


def _variant_section(result: dict[str, Any]) -> dict[str, Any]:
    resolution = result.get("variant_resolution") or result.get("variant_resolution_summary")
    unresolved = []
    placeholders = []
    normalization = (result.get("step_results") or {}).get("normalize_variant")
    if isinstance(normalization, dict):
        unresolved = list(normalization.get("unresolved_fields") or [])
    if isinstance(resolution, dict):
        placeholders = _placeholder_fields(resolution)
    return {
        "normalized": _json_copy(result.get("normalized_variant")),
        "resolved": _json_copy(result.get("resolved_variant")),
        "resolution_summary": _json_copy(resolution),
        "transcript_validation": _json_copy(result.get("transcript_validation")),
        "unresolved_fields": unresolved,
        "placeholder_fields": placeholders,
    }


def _context_section(
    result: dict[str, Any],
    *,
    original_input: dict[str, Any] | None,
    parsed_input: dict[str, Any] | None,
    context_used_for_rating: str | None,
    confirmed_context: dict[str, Any] | None,
    context_candidates: list[Any] | None,
) -> dict[str, Any]:
    source = parsed_input or original_input or {}
    classification = result.get("classification_result") if isinstance(result.get("classification_result"), dict) else {}
    gene_context = (
        source.get("gene_disease_context")
        or source.get("context")
        or (source.get("options") or {}).get("gene_disease_context")
        or classification.get("gene_disease_context")
        or {}
    )
    disease = (
        source.get("disease")
        or source.get("disease_name")
        or gene_context.get("disease")
        or gene_context.get("disease_name")
        or gene_context.get("normalized_disease_name")
    )
    inheritance = (
        source.get("inheritance")
        or source.get("inheritance_mode")
        or gene_context.get("inheritance")
        or gene_context.get("inheritance_mode")
    )
    return {
        "disease": disease,
        "inheritance": inheritance,
        "gene_disease_context": _json_copy(gene_context),
        "context_used_for_rating": context_used_for_rating,
        "context_consistency": _json_copy(result.get("context_consistency")),
        "confirmed_context": _json_copy(confirmed_context),
        "context_candidates": _json_copy(context_candidates or []),
    }


def _runtime_section(result: dict[str, Any], options_used: dict[str, Any]) -> dict[str, Any]:
    data_modes = result.get("data_source_modes") or {}
    return {
        "legacy_mock_mode": bool(result.get("mock_mode", True)),
        "offline_default_mode": bool(result.get("offline_default_mode", True)),
        "data_source_modes_configured": _json_copy(data_modes),
        "data_source_modes_semantics": str(result.get("data_source_modes_semantics") or ""),
        "unresolved_placeholder_mode": bool(result.get("unresolved_placeholder_mode", False)),
        "network_policy": {
            "default_network_enabled": False,
            "online_requested": any(
                bool(options_used.get(key))
                for key in (
                    "use_online_clinvar",
                    "use_online_gnomad",
                    "use_online_vep",
                    "use_online_pubmed",
                    "use_online_litvar",
                    "use_online_search",
                )
            ),
            "online_flags": {
                key: bool(options_used.get(key))
                for key in (
                    "use_online_clinvar",
                    "use_online_gnomad",
                    "use_online_vep",
                    "use_online_pubmed",
                    "use_online_litvar",
                    "use_online_search",
                )
                if key in options_used
            },
        },
        "cache_policy": {
            "cache_dir": options_used.get("provider_cache_dir") or _first_cache_dir(options_used),
            "cache_enabled": bool(options_used.get("provider_cache_dir") or _first_cache_dir(options_used)),
        },
    }


def _providers_section(result: dict[str, Any]) -> dict[str, Any]:
    summary = _json_copy(result.get("provider_mode_summary") or {})
    provider_runtime = ((result.get("step_results") or {}).get("provider_runtime") or {})
    if not isinstance(provider_runtime, dict):
        provider_runtime = {}
    providers = {
        "summary": summary,
        "clinvar": _provider_entry(provider_runtime.get("clinvar") or summary.get("clinvar")),
        "population": _provider_entry(provider_runtime.get("population") or summary.get("population")),
        "computational": _provider_entry(provider_runtime.get("computational") or summary.get("computational")),
        "literature": _provider_entry(provider_runtime.get("literature") or summary.get("literature")),
        "clingen_erepo": _provider_entry(provider_runtime.get("clingen_erepo") or summary.get("clingen_erepo")),
        "transcript": _transcript_provider_entry(result),
        "vcep": _vcep_provider_entry(result),
    }
    return providers


def _provider_entry(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    outcome = payload.get("actual_outcome") or payload.get("outcome") or "skipped"
    provenance = _json_copy(payload.get("provenance") or {})
    raw_hash = payload.get("raw_record_hash") or payload.get("raw_hash")
    provider_mode = provenance.get("provider_mode") or payload.get("provider_mode")
    if raw_hash is not None:
        provenance.setdefault("raw_record_hash", raw_hash)
    if provider_mode is not None:
        provenance.setdefault("provider_mode", provider_mode)
    return {
        "requested_mode": payload.get("requested_mode", "default"),
        "configured_mode": payload.get("configured_mode"),
        "attempted": bool(payload.get("attempted")) if "attempted" in payload else outcome not in {"skipped", None},
        "outcome": outcome,
        "records_count": int(payload.get("records_count") or 0),
        "source_version": payload.get("source_version"),
        "query": _json_copy(payload.get("query")),
        "endpoint": payload.get("endpoint"),
        "cache_hit": payload.get("cache_hit"),
        "limitations": list(payload.get("limitations") or []),
        "provenance": provenance,
        "warnings": list(payload.get("warnings") or []),
        "error_type": payload.get("error_type"),
        "error_message_summary": payload.get("error_message_summary"),
    }


def _transcript_provider_entry(result: dict[str, Any]) -> dict[str, Any]:
    validation = result.get("transcript_validation")
    resolution = result.get("variant_resolution") or {}
    limitations = []
    if isinstance(validation, dict):
        limitations.extend(validation.get("limitations") or [])
    if isinstance(resolution, dict):
        limitations.extend(resolution.get("limitations") or [])
    return {
        "requested_mode": "default",
        "configured_mode": "local_fixture",
        "attempted": bool(validation or resolution),
        "outcome": _status_to_outcome(
            (validation or {}).get("status") if isinstance(validation, dict) else None
        ),
        "records_count": 1 if validation else 0,
        "source_version": _source_version_from_transcript(validation, resolution),
        "query": {},
        "endpoint": None,
        "cache_hit": None,
        "limitations": _unique([str(item) for item in limitations]),
        "provenance": _json_copy((validation or {}).get("provenance") if isinstance(validation, dict) else {}),
    }


def _vcep_provider_entry(result: dict[str, Any]) -> dict[str, Any]:
    vcep = result.get("vcep_signal") or result.get("vcep_override_context")
    limitations = []
    if isinstance(result.get("vcep_signal"), dict):
        limitations.extend(result["vcep_signal"].get("limitations") or [])
        limitations.extend(result["vcep_signal"].get("warnings") or [])
    if isinstance(result.get("vcep_override_context"), dict):
        limitations.extend(result["vcep_override_context"].get("blocked_reasons") or [])
    return {
        "requested_mode": "included" if vcep else "default",
        "configured_mode": "local_profile",
        "attempted": bool(vcep),
        "outcome": "success" if vcep else "skipped",
        "records_count": len((result.get("vcep_signal") or {}).get("matches") or [])
        if isinstance(result.get("vcep_signal"), dict)
        else 0,
        "source_version": None,
        "query": {},
        "endpoint": None,
        "cache_hit": None,
        "limitations": _unique([str(item) for item in limitations]),
        "provenance": _json_copy((result.get("vcep_signal") or {}).get("provenance") if isinstance(result.get("vcep_signal"), dict) else {}),
    }


def _evidence_section(result: dict[str, Any]) -> dict[str, Any]:
    applied = list(result.get("applied_evidence") or [])
    review_note = list(result.get("review_note_evidence") or [])
    reviewed = list(result.get("reviewed_evidence") or [])
    all_items = list(result.get("evidence_items") or [])
    candidate = list(result.get("candidate_evidence") or review_note)
    return {
        "applied": _json_copy(applied),
        "candidate": _json_copy(candidate),
        "review_note": _json_copy(review_note),
        "reviewed": _json_copy(reviewed),
        "all_items": _json_copy(all_items),
        "evidence_status_summary": _evidence_status_summary(all_items, reviewed),
    }


def _evidence_status_summary(items: list[Any], reviewed: list[Any]) -> dict[str, int]:
    summary = {
        "applied": 0,
        "candidate_only": 0,
        "review_note": 0,
        "reviewed_applied": 0,
        "reviewed_rejected": 0,
        "needs_more_info": 0,
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        status = _evidence_status(item)
        summary[status] = summary.get(status, 0) + 1
    for record in reviewed:
        if not isinstance(record, dict):
            continue
        status = str(record.get("evidence_status") or "")
        if status in {"reviewed_applied", "reviewed_rejected", "needs_more_info"}:
            summary[status] = summary.get(status, 0) + 1
    return summary


def _classification_section(result: dict[str, Any]) -> dict[str, Any]:
    classification = result.get("classification_result")
    payload = classification if isinstance(classification, dict) else {}
    return {
        "final_classification": result.get("final_classification") or payload.get("final_classification"),
        "applied_combination_rule": payload.get("applied_combination_rule"),
        "confidence": payload.get("confidence"),
        "classification_result": _json_copy(classification),
        "classification_changed_by_reviewed_evidence": _classification_changed_by_reviewed_evidence(result),
    }


def _review_section(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "human_review_required": bool(result.get("human_review_required", True)),
        "review_flags": _json_copy(result.get("review_flags") or []),
        "review_questions": _review_questions(result),
        "blocking_reasons": _blocking_reasons(result),
    }


def _report_section(result: dict[str, Any], options_used: dict[str, Any]) -> dict[str, Any]:
    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    return {
        "report_text": result.get("report_text") or report.get("content") or "",
        "report_language": report.get("language") or options_used.get("report_language") or "en",
        "report_mode": report.get("mode") or options_used.get("report_mode") or "detailed",
        "report_sections": _report_sections(report),
    }


def _provenance_section(result: dict[str, Any], options_used: dict[str, Any]) -> dict[str, Any]:
    existing = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
    return {
        "run_id": result.get("result_id")
        or (result.get("classification_result") or {}).get("result_id")
        if isinstance(result.get("classification_result"), dict)
        else f"run-{uuid.uuid4()}",
        "timestamp": _timestamp_from_audit(result) or datetime.now(timezone.utc).isoformat(),
        "software_version": _software_version(),
        "parser_versions": _parser_versions(result),
        "data_source_versions": _data_source_versions(result),
        "cache_dir": options_used.get("provider_cache_dir") or _first_cache_dir(options_used),
        **existing,
    }


def _warnings(result: dict[str, Any]) -> list[str]:
    warnings = []
    warnings.extend(str(item) for item in result.get("consistency_warnings") or [])
    variant = result.get("variant_resolution")
    if isinstance(variant, dict):
        warnings.extend(str(item) for item in variant.get("limitations") or [])
    return _unique(warnings)


def _compatibility_section(result: dict[str, Any]) -> dict[str, Any]:
    legacy_fields = [field for field in LEGACY_FIELD_REPLACEMENTS if field in result or field == "candidate_evidence"]
    return {
        "legacy_fields": legacy_fields,
        "canonical_replacements": {
            field: LEGACY_FIELD_REPLACEMENTS[field] for field in legacy_fields
        },
        "deprecation_notice": (
            "Legacy fields remain supported for compatibility. New clients should prefer "
            "the canonical input/variant/context/runtime/providers/evidence/classification/"
            "review/report/provenance sections."
        ),
    }


def _merge_report(existing: Any, canonical_report: dict[str, Any]) -> dict[str, Any]:
    if isinstance(existing, dict):
        return {**existing, **canonical_report}
    return dict(canonical_report)


def _merge_provenance(existing: Any, canonical_provenance: dict[str, Any]) -> dict[str, Any]:
    if isinstance(existing, dict):
        return {**existing, **canonical_provenance}
    return dict(canonical_provenance)


def _empty_text_canonical(
    result: dict[str, Any],
    original_input: dict[str, Any],
    parsed_input: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "status": result.get("status", "error"),
        "tool": result.get("tool", "rate_variant_from_text"),
        "stage": result.get("stage", "natural_language_variant_input"),
        "mock_mode": True,
        "offline_default_mode": True,
        "data_source_modes": {},
        "provider_mode_summary": {},
        "unresolved_placeholder_mode": True,
        "classification_result": None,
        "final_classification": None,
        "evidence_items": [],
        "applied_evidence": [],
        "review_note_evidence": [],
        "reviewed_evidence": [],
        "limitations": [],
        "review_flags": [],
        "report_text": "",
        "report": {},
    }
    return build_rate_variant_canonical_output(
        base,
        original_input=original_input,
        parsed_input=parsed_input,
        input_type="natural_language_text",
        context_used_for_rating=result.get("context_used_for_rating"),
        confirmed_context=_dict_or_none(result.get("confirmed_context")),
        context_candidates=list(result.get("context_candidates") or []),
    )


def _options_used(
    original_input: dict[str, Any] | None,
    parsed_input: dict[str, Any] | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    for source in (parsed_input, original_input):
        if isinstance(source, dict) and isinstance(source.get("options"), dict):
            return _json_copy(source["options"])
    return _options_from_runtime(result)


def _options_from_runtime(result: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {"mock_mode": bool(result.get("mock_mode", True))}
    if isinstance(result.get("report"), dict):
        if result["report"].get("language"):
            options["report_language"] = result["report"]["language"]
        if result["report"].get("mode"):
            options["report_mode"] = result["report"]["mode"]
    return options


def _infer_input_type(
    original_input: dict[str, Any] | None,
    parsed_input: dict[str, Any] | None,
    result: dict[str, Any],
) -> str:
    source = parsed_input or original_input or {}
    if "text" in source:
        return "natural_language_text"
    if source.get("input_type"):
        return str(source["input_type"])
    if isinstance(source.get("variant"), dict):
        return str(source["variant"].get("input_type") or "structured")
    if result.get("normalized_variant"):
        variant = result["normalized_variant"]
        if isinstance(variant, dict) and all(variant.get(key) for key in ("chrom", "pos", "ref", "alt")):
            return "vcf_like"
    return "structured"


def _placeholder_fields(resolution: dict[str, Any]) -> list[str]:
    placeholders = []
    resolved = resolution.get("resolved_variant")
    if isinstance(resolved, dict):
        for field in ("chrom", "pos", "ref", "alt", "hgvs_g", "hgvs_p"):
            value = resolved.get(field)
            if value in (None, "", "N", 0) or str(value).lower().startswith("placeholder"):
                placeholders.append(field)
    return _unique(placeholders)


def _first_cache_dir(options: dict[str, Any]) -> str | None:
    data_sources = options.get("data_sources")
    if not isinstance(data_sources, dict):
        return None
    sources = data_sources.get("sources") or data_sources.get("data_sources") or {}
    if not isinstance(sources, dict):
        return None
    for source in sources.values():
        if isinstance(source, dict) and source.get("cache_dir"):
            return str(source["cache_dir"])
    return None


def _status_to_outcome(status: str | None) -> str:
    if status in {"ok", "resolved", "warning", "conflict", "partial"}:
        return "success"
    if status in {"insufficient", "unresolved"}:
        return "no_record"
    if status == "error":
        return "failure"
    return "skipped"


def _source_version_from_transcript(validation: Any, resolution: Any) -> str | None:
    if isinstance(validation, dict):
        matched = validation.get("matched_record")
        if isinstance(matched, dict) and matched.get("source_version"):
            return str(matched["source_version"])
    if isinstance(resolution, dict):
        for item in resolution.get("provenance") or []:
            if isinstance(item, dict) and item.get("source_version"):
                return str(item["source_version"])
    return None


def _evidence_status(item: dict[str, Any]) -> str:
    supporting = item.get("supporting_data") if isinstance(item.get("supporting_data"), dict) else {}
    status = supporting.get("evidence_status")
    if status in {"reviewed_applied", "reviewed_rejected", "needs_more_info"}:
        return str(status)
    if (
        item.get("candidate_only")
        or item.get("applied") is False
        or str(item.get("strength")) == "none"
        or supporting.get("candidate_only")
        or supporting.get("evidence_status") == "candidate"
        or supporting.get("applied") is False
    ):
        return "review_note" if supporting.get("review_note") else "candidate_only"
    return "applied"


def _classification_changed_by_reviewed_evidence(result: dict[str, Any]) -> bool:
    return any(
        isinstance(item, dict) and item.get("source", {}).get("name") == "manual_reviewed_evidence"
        for item in result.get("applied_evidence") or []
    )


def _review_questions(result: dict[str, Any]) -> list[str]:
    questions = []
    literature = (result.get("step_results") or {}).get("search_and_summarize_literature")
    if isinstance(literature, dict):
        questions.extend(str(item) for item in literature.get("review_questions") or [])
    return _unique(questions)


def _blocking_reasons(result: dict[str, Any]) -> list[str]:
    reasons = []
    for item in result.get("evidence_items") or []:
        if not isinstance(item, dict):
            continue
        supporting = item.get("supporting_data") if isinstance(item.get("supporting_data"), dict) else {}
        reasons.extend(str(reason) for reason in supporting.get("blocking_reasons") or [])
    return _unique(reasons)


def _report_sections(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    if isinstance(summary, dict):
        return {
            "summary": summary,
            "triggered_acmg_evidence": summary.get("triggered_acmg_evidence") or [],
            "candidate_acmg_evidence": summary.get("candidate_acmg_evidence") or [],
            "limitations": summary.get("limitations") or [],
        }
    content = report.get("content")
    return {"content": content} if content is not None else {}


def _timestamp_from_audit(result: dict[str, Any]) -> str | None:
    audit = result.get("audit_trail")
    if isinstance(audit, list) and audit:
        event_id = str((audit[-1] or {}).get("event_id") or "")
        if event_id:
            return None
    return None


def _software_version() -> str:
    try:
        return metadata.version("variant-pathogenicity-rater-mcp")
    except metadata.PackageNotFoundError:
        version_path = Path(__file__).resolve().parents[3] / "VERSION"
        if version_path.exists():
            return version_path.read_text(encoding="utf-8").strip()
    return "unknown"


def _parser_versions(result: dict[str, Any]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for item in _iter_sources(result):
        provenance = item.get("provenance") if isinstance(item, dict) else None
        if isinstance(provenance, dict) and provenance.get("parser_version"):
            versions[str(provenance.get("data_source") or item.get("name") or "source")] = str(
                provenance["parser_version"]
            )
    return versions


def _data_source_versions(result: dict[str, Any]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for item in _iter_sources(result):
        if isinstance(item, dict) and item.get("name") and item.get("version"):
            versions[str(item["name"])] = str(item["version"])
        provenance = item.get("provenance") if isinstance(item, dict) else None
        if isinstance(provenance, dict) and provenance.get("data_source") and provenance.get("source_version"):
            versions[str(provenance["data_source"])] = str(provenance["source_version"])
    for name, provider in (result.get("provider_mode_summary") or {}).items():
        if isinstance(provider, dict) and provider.get("source_version"):
            versions[str(name)] = str(provider["source_version"])
    return versions


def _iter_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    sources = []
    for item in result.get("evidence_items") or []:
        if isinstance(item, dict) and isinstance(item.get("source"), dict):
            sources.append(item["source"])
    return sources


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return _json_copy(value) if isinstance(value, dict) else None


def _json_copy(value: Any) -> Any:
    return copy.deepcopy(value)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
