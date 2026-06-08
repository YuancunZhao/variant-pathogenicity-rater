from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from variant_pathogenicity_rater.schemas.common import AuditTrail
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.variant_resolution import VariantResolutionResult, resolve_variant


RunStep = Callable[[str, list[AuditTrail], list[str], Callable[[], Any]], Any | None]


@dataclass(frozen=True)
class ResolutionPhaseResult:
    normalized_variant: Variant
    context: GeneDiseaseContext
    variant_resolution: VariantResolutionResult | None


def run_resolution_phase(
    *,
    arguments: dict[str, Any],
    options: dict[str, Any],
    normalized_variant: Variant,
    context: GeneDiseaseContext,
    audit_trail: list[AuditTrail],
    limitations: list[str],
    step_results: dict[str, Any],
    run_step: RunStep,
) -> ResolutionPhaseResult:
    resolution_options = dict(options)
    if _manual_nmd_context_supplied(arguments):
        resolution_options["preserve_manual_nmd_context"] = True

    variant_resolution = run_step(
        "resolve_variant",
        audit_trail,
        limitations,
        lambda: resolve_variant(
            normalized_variant,
            context=context,
            options=resolution_options,
        ),
    )
    if variant_resolution is not None:
        limitations.extend(variant_resolution.limitations)
        if variant_resolution.resolved_variant is not None:
            normalized_variant = variant_resolution.resolved_variant
        if variant_resolution.resolved_context is not None:
            context = variant_resolution.resolved_context
        step_results["resolve_variant"] = variant_resolution.model_dump(mode="json")

    return ResolutionPhaseResult(
        normalized_variant=normalized_variant,
        context=context,
        variant_resolution=variant_resolution,
    )


def _manual_nmd_context_supplied(arguments: dict[str, Any]) -> bool:
    context_payload = (
        arguments.get("gene_disease_context")
        or arguments.get("context")
        or arguments.get("options", {}).get("gene_disease_context")
        or {}
    )
    if not isinstance(context_payload, dict):
        return False
    return any(
        key in context_payload
        for key in (
            "last_exon_information",
            "nmd_prediction_available",
            "nmd_predicted",
        )
    )
