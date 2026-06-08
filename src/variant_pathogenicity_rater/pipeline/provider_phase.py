from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from variant_pathogenicity_rater.data_sources.config import DataSourcesConfig
from variant_pathogenicity_rater.providers import (
    ProviderExecutionPlan,
    build_provider_execution_plan,
    build_variant_identity,
)
from variant_pathogenicity_rater.schemas.variant import Variant


@dataclass(frozen=True)
class ProviderPhaseResult:
    provider_identity: Any
    provider_execution_plan: ProviderExecutionPlan


def run_provider_phase(
    *,
    options: dict[str, Any],
    data_sources_config: DataSourcesConfig,
    original_normalized_variant: Variant,
    variant_resolution: Any = None,
    step_results: dict[str, Any],
) -> ProviderPhaseResult:
    provider_identity = build_variant_identity(
        normalized_variant=original_normalized_variant,
        variant_resolution=variant_resolution,
        explicit_aliases=options.get("provider_identity_aliases"),
    )
    step_results["provider_identity"] = provider_identity.model_dump(mode="json")

    # 79A-3C: build the execution plan once in provider_phase so
    # evidence_phase can reuse its dependency checks.
    plan = build_provider_execution_plan(
        identity=provider_identity,
        options=options,
        data_sources_config=data_sources_config,
    )
    step_results["provider_execution_plan"] = plan.model_dump(mode="json")

    return ProviderPhaseResult(
        provider_identity=provider_identity,
        provider_execution_plan=plan,
    )
