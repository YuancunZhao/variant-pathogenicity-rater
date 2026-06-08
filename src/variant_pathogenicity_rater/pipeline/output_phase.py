from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from variant_pathogenicity_rater.data_sources.config import DataSourcesConfig
from variant_pathogenicity_rater.data_sources.provider_result import (
    build_provider_runtime_results,
    provider_runtime_results_to_json,
    provider_summary_from_runtime_results,
)
from variant_pathogenicity_rater.evidence.status import split_evidence_by_status
from variant_pathogenicity_rater.pipeline.output_schema import add_rate_variant_canonical_fields
from variant_pathogenicity_rater.providers import build_variant_identity
from variant_pathogenicity_rater.reporting import generate_report
from variant_pathogenicity_rater.schemas.classification import ClassificationResult
from variant_pathogenicity_rater.schemas.common import AuditTrail
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem
from variant_pathogenicity_rater.schemas.variant import Variant
from variant_pathogenicity_rater.vcep_profiles import override_provenance


HUMAN_REVIEW_NOTICE = (
    "Human review is required. This framework does not provide a final clinical assertion."
)


RunStep = Callable[[str, list[AuditTrail], list[str], Callable[[], Any]], Any | None]


def build_rate_variant_output(
    *,
    arguments: dict[str, Any],
    options: dict[str, Any],
    data_sources_config: DataSourcesConfig,
    audit_trail: list[AuditTrail],
    limitations: list[str],
    step_results: dict[str, Any],
    run_step: RunStep,
    original_normalized_variant: Variant,
    normalized_variant: Variant,
    classification_result: ClassificationResult,
    evidence_items: list[EvidenceItem],
    reviewed_evidence_records: list[dict[str, Any]],
    provider_dependency_checks: dict[str, Any],
    transcript_selection: Any = None,
    transcript_validation: Any = None,
    variant_resolution: Any = None,
    context_consistency: Any = None,
    clingen_erepo_result: Any = None,
    vcep_signal_result: Any = None,
    vcep_override_context: Any = None,
) -> dict[str, Any]:
    applied_evidence = _applied_evidence_items(evidence_items)
    review_note_evidence = _review_note_evidence_items(evidence_items)
    normalization_identity = (step_results.get("normalize_variant") or {}).get("variant_identity")

    # Finalize classification_result state before report generation so the
    # report sees the complete limitations list.
    classification_result.limitations = _unique(limitations)

    report = run_step(
        "generate_report",
        audit_trail,
        limitations,
        lambda: generate_report(
            classification_result,
            mode=options.get("report_mode", "detailed"),
            language=options.get("report_language", "en"),
        ),
    )
    if report is None:
        report = {
            "format": "json",
            "report_text": classification_result.report_text,
            "limitations": _unique(limitations),
            "human_review_required": True,
        }
    if hasattr(report, "content") and hasattr(report, "model_dump_json"):
        classification_result.report_text = str(report.content)
        serialized_report = json.loads(report.model_dump_json())
    else:
        classification_result.report_text = str(report["report_text"])
        serialized_report = report
    step_results["generate_report"] = serialized_report
    combined_audit = audit_trail + classification_result.audit_trail

    provider_runtime_results = build_provider_runtime_results(
        data_sources_config,
        step_results,
        options,
    )
    provider_mode_summary = provider_summary_from_runtime_results(provider_runtime_results)
    step_results["provider_runtime"] = provider_runtime_results_to_json(provider_runtime_results)
    provider_identity = build_variant_identity(
        normalized_variant=original_normalized_variant,
        variant_resolution=variant_resolution,
        explicit_aliases=options.get("provider_identity_aliases"),
    )
    step_results["provider_identity"] = provider_identity.model_dump(mode="json")
    step_results["provider_dependency_checks"] = provider_dependency_checks
    # 79A-3C: provider_execution_plan is built in provider_phase and
    # reused in evidence_phase.  output_phase preserves it but does
    # not rebuild it.  ProviderRuntimeResult construction must not
    # read the plan.

    output = {
        "status": "ok",
        "tool": "rate_variant",
        "stage": "integrated_snv_small_indel_acmg_pipeline",
        "mock_mode": bool(options.get("mock_mode", True)),
        "offline_default_mode": bool(data_sources_config.offline_default),
        "data_source_modes": {
            name: source.mode for name, source in data_sources_config.sources.items()
        },
        "data_source_modes_semantics": (
            "Configured/requested provider modes after runtime options are applied; "
            "actual provider outcomes are recorded in step_results.provider_runtime "
            "(provider_mode_summary is a legacy compatibility view)."
        ),
        "provider_mode_summary": provider_mode_summary,
        "unresolved_placeholder_mode": _unresolved_placeholder_mode(step_results),
        "normalized_variant": json.loads(original_normalized_variant.model_dump_json()),
        "resolved_variant": json.loads(
            (
                variant_resolution.resolved_variant
                if variant_resolution is not None and variant_resolution.resolved_variant is not None
                else normalized_variant
            ).model_dump_json()
        ),
        "variant_resolution": (
            variant_resolution.model_dump(mode="json")
            if variant_resolution is not None
            else None
        ),
        "provider_identity": provider_identity.model_dump(mode="json"),
        "provider_dependency_checks": provider_dependency_checks,
        "normalization_identity": normalization_identity,
        "classification_result": json.loads(classification_result.model_dump_json()),
        "evidence_items": [json.loads(item.model_dump_json()) for item in evidence_items],
        "applied_evidence": [json.loads(item.model_dump_json()) for item in applied_evidence],
        "review_note_evidence": [
            json.loads(item.model_dump_json()) for item in review_note_evidence
        ],
        "reviewed_evidence": reviewed_evidence_records,
        "clingen_erepo": (
            json.loads(clingen_erepo_result.model_dump_json())
            if clingen_erepo_result is not None
            else None
        ),
        "clingen_erepo_reviewed_evidence_drafts": (
            [
                json.loads(draft.model_dump_json())
                for draft in clingen_erepo_result.reviewed_evidence_drafts
            ]
            if clingen_erepo_result is not None
            else []
        ),
        "vcep_signal": (
            vcep_signal_result.model_dump(mode="json")
            if vcep_signal_result is not None
            else None
        ),
        "vcep_override_context": (
            vcep_override_context.model_dump(mode="json")
            if vcep_override_context is not None
            else None
        ),
        "final_classification": classification_result.final_classification,
        "transcript_selection": (
            json.loads(transcript_selection.model_dump_json())
            if transcript_selection is not None
            else None
        ),
        "transcript_validation": (
            json.loads(transcript_validation.model_dump_json())
            if transcript_validation is not None
            else None
        ),
        "variant_resolution_summary": (
            variant_resolution.model_dump(mode="json")
            if variant_resolution is not None
            else None
        ),
        "context_consistency": (
            json.loads(context_consistency.model_dump_json())
            if context_consistency is not None
            else None
        ),
        "consistency_warnings": (
            [json.loads(check.model_dump_json()) for check in context_consistency.warnings]
            if context_consistency is not None
            else []
        ),
        "report_text": classification_result.report_text,
        "report": serialized_report,
        "limitations": classification_result.limitations,
        "review_flags": [
            json.loads(flag.model_dump_json()) for flag in classification_result.review_flags
        ],
        "provenance": _provenance_summary(
            evidence_items,
            normalization_identity=normalization_identity,
            transcript_selection=transcript_selection,
            transcript_validation=transcript_validation,
            variant_resolution=variant_resolution,
            context_consistency=context_consistency,
            vcep_override_context=vcep_override_context,
        ),
        "human_review_required": True,
        "human_review": {"required": True, "notice": HUMAN_REVIEW_NOTICE},
        "audit_trail": [json.loads(event.model_dump_json()) for event in combined_audit],
        "step_results": step_results,
    }
    return add_rate_variant_canonical_fields(output, original_input=arguments)


def failed_normalization_response(
    arguments: dict[str, Any],
    audit_trail: list[AuditTrail],
    limitations: list[str],
    step_results: dict[str, Any],
) -> dict[str, Any]:
    output = {
        "status": "error",
        "tool": "rate_variant",
        "stage": "variant_normalization",
        "mock_mode": True,
        "normalized_variant": None,
        "classification_result": None,
        "evidence_items": [],
        "final_classification": None,
        "report_text": "Variant normalization failed. Human review is required.",
        "limitations": _unique(limitations),
        "human_review_required": True,
        "human_review": {"required": True, "notice": HUMAN_REVIEW_NOTICE},
        "audit_trail": [json.loads(event.model_dump_json()) for event in audit_trail],
        "step_results": step_results,
        "input": arguments,
    }
    return add_rate_variant_canonical_fields(output, original_input=arguments)


def _applied_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return list(split_evidence_by_status(items)["applied"])


def _review_note_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return list(split_evidence_by_status(items)["review_note"])


def _provenance_summary(
    items: list[EvidenceItem],
    *,
    normalization_identity: Any,
    transcript_selection: Any,
    transcript_validation: Any,
    variant_resolution: Any,
    context_consistency: Any,
    vcep_override_context: Any = None,
) -> dict[str, Any]:
    return {
        "normalization_identity": normalization_identity if isinstance(normalization_identity, dict) else None,
        "evidence_sources": [
            {
                "evidence_id": item.evidence_id,
                "source": item.source.name,
                "version": item.source.version,
                "retrieval_timestamp": item.source.retrieval_timestamp,
                "query": item.source.query,
                "raw_snapshot_ref": item.source.raw_snapshot_ref,
                "candidate_only": item.candidate_only,
                "applied": item.applied,
            }
            for item in items
        ],
        "transcript_selection": (
            transcript_selection.provenance if transcript_selection is not None else None
        ),
        "transcript_validation": (
            transcript_validation.provenance if transcript_validation is not None else None
        ),
        "variant_resolution": (
            variant_resolution.provenance if variant_resolution is not None else None
        ),
        "context_consistency": (
            context_consistency.provenance if context_consistency is not None else None
        ),
        "vcep_override": override_provenance(vcep_override_context),
    }


def _provider_limitations(step_payload: Any) -> list[str]:
    if not isinstance(step_payload, dict):
        return []
    limitations = [str(item) for item in step_payload.get("limitations") or [] if item]
    summary = step_payload.get("summary")
    if isinstance(summary, dict):
        decision = summary.get("decision")
        if isinstance(decision, dict):
            limitations.extend(str(item) for item in decision.get("limitations") or [] if item)
        for call in summary.get("predictor_calls") or []:
            if isinstance(call, dict):
                limitations.extend(str(item) for item in call.get("limitations") or [] if item)
    return _unique(limitations)


def _unresolved_placeholder_mode(step_results: dict[str, Any]) -> bool:
    resolution = step_results.get("resolve_variant")
    if isinstance(resolution, dict) and resolution.get("status") in {"partial", "unresolved", "error"}:
        return True
    for step in step_results.values():
        if not isinstance(step, dict):
            continue
        if any("placeholder" in limitation.lower() for limitation in _provider_limitations(step)):
            return True
        if step.get("prediction") == "unavailable":
            return True
        summary = step.get("summary")
        if isinstance(summary, dict):
            for call in summary.get("predictor_calls") or []:
                if isinstance(call, dict) and call.get("prediction") == "unavailable":
                    return True
    return False


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
