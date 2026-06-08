from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.data_sources.config import load_data_sources_config
from variant_pathogenicity_rater.data_sources.providers import build_population_provider
from variant_pathogenicity_rater.literature_agent import search_and_summarize_literature
from variant_pathogenicity_rater.pipeline.classification_phase import run_classification_phase
from variant_pathogenicity_rater.pipeline.evidence_phase import run_evidence_phase
from variant_pathogenicity_rater.pipeline.normalization_phase import run_normalization_phase
from variant_pathogenicity_rater.pipeline.output_phase import (
    HUMAN_REVIEW_NOTICE,
    build_rate_variant_output,
    failed_normalization_response,
)
from variant_pathogenicity_rater.pipeline.provider_phase import run_provider_phase
from variant_pathogenicity_rater.pipeline.resolution_phase import run_resolution_phase
from variant_pathogenicity_rater.runtime.options import (
    normalize_runtime_options,
    runtime_options_to_pipeline_dict,
)
from variant_pathogenicity_rater.schemas.common import AuditTrail


def rate_variant(arguments: dict[str, Any]) -> dict[str, Any]:
    options = _options(arguments)
    data_sources_config = load_data_sources_config(overrides=options.get("data_sources"))
    audit_trail: list[AuditTrail] = []
    limitations: list[str] = [
        "Mock mode is enabled by default; no network access was attempted.",
        "Phase 1 supports SNV and small indel variants only.",
        "All conclusions are machine proposals and require qualified human review.",
    ]
    step_results: dict[str, Any] = {}

    normalization_phase = run_normalization_phase(
        arguments=arguments,
        audit_trail=audit_trail,
        limitations=limitations,
        step_results=step_results,
        run_step=_run_step,
        audit_event=_audit,
    )
    if normalization_phase.normalization_failed:
        return failed_normalization_response(arguments, audit_trail, limitations, step_results)

    normalized_variant = normalization_phase.normalized_variant
    original_normalized_variant = normalization_phase.original_normalized_variant
    context = normalization_phase.context

    resolution_phase = run_resolution_phase(
        arguments=arguments,
        options=options,
        normalized_variant=normalized_variant,
        context=context,
        audit_trail=audit_trail,
        limitations=limitations,
        step_results=step_results,
        run_step=_run_step,
    )
    normalized_variant = resolution_phase.normalized_variant
    context = resolution_phase.context
    variant_resolution = resolution_phase.variant_resolution

    provider_phase = run_provider_phase(
        options=options,
        original_normalized_variant=original_normalized_variant,
        variant_resolution=variant_resolution,
        step_results=step_results,
    )
    provider_identity = provider_phase.provider_identity

    evidence_phase = run_evidence_phase(
        arguments=arguments,
        options=options,
        data_sources_config=data_sources_config,
        normalized_variant=normalized_variant,
        context=context,
        variant_resolution=variant_resolution,
        provider_identity=provider_identity,
        audit_trail=audit_trail,
        limitations=limitations,
        step_results=step_results,
        run_step=_run_step,
        audit_event=_audit,
        population_provider_builder=build_population_provider,
        literature_summarizer=search_and_summarize_literature,
    )
    evidence_items = evidence_phase.evidence_items
    context_consistency = evidence_phase.context_consistency
    transcript_selection = evidence_phase.transcript_selection
    transcript_validation = evidence_phase.transcript_validation
    variant_resolution = evidence_phase.variant_resolution
    reviewed_evidence_records = evidence_phase.reviewed_evidence_records
    reviewed_review_flags = evidence_phase.reviewed_review_flags
    provider_dependency_review_flags = evidence_phase.provider_dependency_review_flags
    provider_dependency_checks = evidence_phase.provider_dependency_checks
    vcep_signal_result = evidence_phase.vcep_signal_result
    vcep_override_context = evidence_phase.vcep_override_context
    clingen_erepo_result = evidence_phase.clingen_erepo_result

    classification_phase = run_classification_phase(
        evidence_items=evidence_items,
        normalized_variant=normalized_variant,
        context=context,
        limitations=limitations,
        audit_trail=audit_trail,
        step_results=step_results,
        run_step=_run_step,
        transcript_selection=transcript_selection,
        transcript_validation=transcript_validation,
        variant_resolution=variant_resolution,
        context_consistency=context_consistency,
        provider_dependency_review_flags=provider_dependency_review_flags,
        reviewed_review_flags=reviewed_review_flags,
        clingen_erepo_result=clingen_erepo_result,
        vcep_signal_result=vcep_signal_result,
        vcep_override_context=vcep_override_context,
    )
    classification_result = classification_phase.classification_result
    return build_rate_variant_output(
        arguments=arguments,
        options=options,
        data_sources_config=data_sources_config,
        audit_trail=audit_trail,
        limitations=limitations,
        step_results=step_results,
        run_step=_run_step,
        original_normalized_variant=original_normalized_variant,
        normalized_variant=normalized_variant,
        classification_result=classification_result,
        evidence_items=evidence_items,
        reviewed_evidence_records=reviewed_evidence_records,
        provider_dependency_checks=provider_dependency_checks,
        transcript_selection=transcript_selection,
        transcript_validation=transcript_validation,
        variant_resolution=variant_resolution,
        context_consistency=context_consistency,
        clingen_erepo_result=clingen_erepo_result,
        vcep_signal_result=vcep_signal_result,
        vcep_override_context=vcep_override_context,
    )


def _run_step(
    step_name: str,
    audit_trail: list[AuditTrail],
    limitations: list[str],
    func: Callable[[], Any],
) -> Any | None:
    audit_trail.append(_audit(step_name, "started"))
    try:
        result = func()
    except Exception as exc:  # noqa: BLE001 - pipeline must preserve failure as limitation.
        limitations.append(f"{step_name} failed: {exc.__class__.__name__}: {exc}")
        audit_trail.append(_audit(step_name, "failed", [str(exc)]))
        return None
    audit_trail.append(_audit(step_name, "completed"))
    return result


def _options(arguments: dict[str, Any]) -> dict[str, Any]:
    runtime_options = normalize_runtime_options(arguments.get("options") or {})
    return runtime_options_to_pipeline_dict(runtime_options)


def _normalize_online_provider_options(options: dict[str, Any]) -> dict[str, Any]:
    runtime_options = normalize_runtime_options(options)
    return runtime_options_to_pipeline_dict(runtime_options)


def _audit(step_name: str, status: str, notes: list[str] | None = None) -> AuditTrail:
    return AuditTrail(
        event_id=f"audit-{step_name}-{status}-{datetime.now(timezone.utc).timestamp():.6f}",
        event_type=f"{step_name}_{status}",
        tool_name=step_name,
        notes=notes or [],
    )
