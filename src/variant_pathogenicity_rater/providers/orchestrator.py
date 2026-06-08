"""79A-3A — Provider orchestrator contract scaffold.

Defines the current provider dependency graph and execution-plan
observability without replacing any provider execution path.

This module is **contract-only**. It does not route, schedule, or
execute provider calls. It only describes what the current pipeline
already does so that a future orchestrator has a clean contract to
build on.

Hard constraints (do not remove):
- ``ProviderRuntimeResult`` remains the only provider runtime outcome
  source.
- Invalid gnomAD identity remains ``skipped``, not ``no_record``, and
  must not trigger PM2.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.data_sources.config import DataSourcesConfig, ProviderMode
from variant_pathogenicity_rater.providers.dependencies import (
    ProviderDependencyCheck,
    check_clinvar_dependency,
    check_gnomad_dependency,
    check_literature_dependency,
    check_vep_dependency,
)
from variant_pathogenicity_rater.providers.identity import VariantIdentity
from variant_pathogenicity_rater.schemas.common import SchemaModel


class ProviderNodeKind(StrEnum):
    """Categorises provider nodes by their role in the pipeline."""

    IDENTITY = "identity"
    POPULATION = "population"
    COMPUTATIONAL = "computational"
    CLINICAL_ASSERTION = "clinical_assertion"
    LITERATURE = "literature"
    RUNTIME_OBSERVABILITY = "runtime_observability"


class ProviderExecutionNode(SchemaModel):
    """A single provider node in the execution plan.

    Describes what the node is, whether its dependency is satisfied,
    and what the planned execution path looks like under the current
    options/config.  This is **observability only** — it does not
    change whether or how the node is actually executed.
    """

    node_key: str = Field(..., min_length=1)
    """Stable key matching a step_results slot (e.g. ``query_clinvar``)."""

    provider_name: str = Field(..., min_length=1)
    """Logical provider name (e.g. ``clinvar``, ``population``)."""

    kind: ProviderNodeKind
    """Provider category for grouping / readability."""

    enabled: bool = True
    """Whether this node is included per runtime options.

    Controlled by ``include_population``, ``include_computational``,
    ``include_clinvar``, ``include_literature``, and
    ``include_clingen_erepo`` flags.  Identity and provider_runtime
    are always enabled.
    """

    dependency_check: ProviderDependencyCheck | None = None
    """Dependency result for this node (None when the node has no
    dependency gate, e.g. provider_identity)."""

    configured_mode: str = "mock"
    """Effective configured mode from DataSourcesConfig."""

    requested_mode: str = "default"
    """Requested mode derived from runtime options."""

    planned_attempt: bool = False
    """Whether the current pipeline would enter/execute this step.

    True when the node is enabled and either (a) the source is not
    gated by an online-only dependency check, or (b) the dependency
    is satisfied under the relevant execution path.

    This includes mock, local-file, and inline-prediction provider
    paths — it is NOT limited to online request attempts.
    """

    notes: list[str] = Field(default_factory=list)
    """Human-readable notes about this node's role / constraints."""


class ProviderExecutionPlan(SchemaModel):
    """Observability-only execution plan for the current provider graph.

    Describes every provider node the pipeline currently knows about,
    plus a summary of which nodes would be skipped due to dependency
    gates.  This plan is additive — no consumer (report, benchmark,
    classification) is required to read it.
    """

    plan_version: str = "79A-3A-v1"

    provider_identity: VariantIdentity | None = None
    """Snapshot of the provider-layer identity used for dependency checks."""

    nodes: list[ProviderExecutionNode] = Field(default_factory=list)
    """Ordered list of provider nodes in pipeline execution order."""

    dependency_unsatisfied: list[str] = Field(default_factory=list)
    """Node keys whose dependency check exists and is NOT satisfied.

    This is a pure check result — it does not mean the pipeline
    actually skips the node.  A node may have an unsatisfied dependency
    but still be attempted when the source is not online (mock/local).
    """

    dependency_skip_planned: list[str] = Field(default_factory=list)
    """Node keys that the current pipeline would actually skip because
    the dependency is unsatisfied under the relevant execution path.

    This is a subset of ``dependency_unsatisfied`` — only nodes where
    the source is online and the dependency gate is enforced.
    """

    dependency_skipped: list[str] = Field(default_factory=list)
    """Alias for ``dependency_skip_planned`` (legacy compatibility)."""

    attempted: list[str] = Field(default_factory=list)
    """Node keys that would be attempted under the current config."""

    summary: dict[str, Any] = Field(default_factory=dict)
    """Aggregated counts: total, enabled, dependency_unsatisfied,
    dependency_skip_planned, attempted, per-kind."""


_DEFAULT_ENABLED = True


def build_provider_execution_plan(
    identity: VariantIdentity,
    options: dict[str, Any],
    data_sources_config: DataSourcesConfig,
) -> ProviderExecutionPlan:
    """Build the current provider execution plan from existing contracts.

    This reuses the existing dependency checks — ``check_gnomad_dependency``,
    ``check_vep_dependency``, ``check_clinvar_dependency``,
    ``check_literature_dependency`` — and the current per-source config so
    the plan accurately reflects what the pipeline already does.

    The returned plan is **additive observability only**.  It must not
    be used to route or gate provider execution at this stage.
    """
    nodes: list[ProviderExecutionNode] = []

    # ── provider_identity ──────────────────────────────────────────
    nodes.append(
        ProviderExecutionNode(
            node_key="provider_identity",
            provider_name="identity",
            kind=ProviderNodeKind.IDENTITY,
            enabled=True,
            dependency_check=None,
            configured_mode="always",
            requested_mode="always",
            planned_attempt=True,
            notes=["Provider-layer identity is always built from normalized + resolved variant state."],
        )
    )

    # ── gnomAD / population ────────────────────────────────────────
    pop_enabled = options.get("include_population", _DEFAULT_ENABLED)
    gnomad_check = check_gnomad_dependency(identity)
    pop_cfg = data_sources_config.source("population")
    pop_requested = _requested_mode(options, "use_online_gnomad", "population")
    pop_online = _online_source(data_sources_config, "population")
    # dependency-skip only when online source AND dependency unsatisfied
    pop_dep_skip = pop_online and not gnomad_check.satisfied
    pop_attempt = pop_enabled and not pop_dep_skip
    nodes.append(
        ProviderExecutionNode(
            node_key="query_population_frequency",
            provider_name="population",
            kind=ProviderNodeKind.POPULATION,
            enabled=pop_enabled,
            dependency_check=gnomad_check,
            configured_mode=str(pop_cfg.mode),
            requested_mode=pop_requested,
            planned_attempt=pop_attempt,
            notes=[
                "Invalid/missing gnomAD identity → skipped (not no_record); must not trigger PM2.",
                "Mock/local paths attempt regardless of dependency; only online source enforces the gate.",
            ],
        )
    )

    # ── VEP / computational ────────────────────────────────────────
    comp_enabled = options.get("include_computational", _DEFAULT_ENABLED)
    vep_check = check_vep_dependency(identity)
    comp_cfg = data_sources_config.source("computational")
    comp_requested = _requested_mode(options, "use_online_vep", "computational")
    comp_online = _online_source(data_sources_config, "computational")
    has_inline_predictions = bool(options.get("computational_predictions") is not None)
    # dependency-skip ONLY when no inline predictions AND online AND dependency unsatisfied
    comp_dep_skip = (
        not has_inline_predictions
        and comp_online
        and not vep_check.satisfied
    )
    comp_attempt = comp_enabled and not comp_dep_skip
    nodes.append(
        ProviderExecutionNode(
            node_key="evaluate_computational_evidence",
            provider_name="computational",
            kind=ProviderNodeKind.COMPUTATIONAL,
            enabled=comp_enabled,
            dependency_check=vep_check,
            configured_mode=str(comp_cfg.mode),
            requested_mode=comp_requested,
            planned_attempt=comp_attempt,
            notes=[
                "VEP/REVEL/CADD predictions; computational consensus is supporting-level only.",
                "Inline ``computational_predictions`` bypass the online dependency gate.",
            ],
        )
    )

    # ── ClinVar ────────────────────────────────────────────────────
    clinvar_enabled = options.get("include_clinvar", _DEFAULT_ENABLED)
    clinvar_check = check_clinvar_dependency(identity)
    clinvar_cfg = data_sources_config.source("clinvar")
    clinvar_requested = _requested_mode(options, "use_online_clinvar", "clinvar")
    clinvar_online = _online_source(data_sources_config, "clinvar")
    clinvar_dep_skip = clinvar_online and not clinvar_check.satisfied
    clinvar_attempt = clinvar_enabled and not clinvar_dep_skip
    nodes.append(
        ProviderExecutionNode(
            node_key="query_clinvar",
            provider_name="clinvar",
            kind=ProviderNodeKind.CLINICAL_ASSERTION,
            enabled=clinvar_enabled,
            dependency_check=clinvar_check,
            configured_mode=str(clinvar_cfg.mode),
            requested_mode=clinvar_requested,
            planned_attempt=clinvar_attempt,
            notes=["ClinVar records are review-note/candidate-only unless explicitly promoted through reviewed evidence."],
        )
    )

    # ── ClinGen ERepo ──────────────────────────────────────────────
    erepo_enabled = bool(options.get("include_clingen_erepo", False))
    erepo_cfg = data_sources_config.source("clingen_erepo")
    erepo_requested = "included" if erepo_enabled else "default"
    nodes.append(
        ProviderExecutionNode(
            node_key="query_clingen_erepo",
            provider_name="clingen_erepo",
            kind=ProviderNodeKind.CLINICAL_ASSERTION,
            enabled=erepo_enabled,
            dependency_check=None,
            configured_mode=str(erepo_cfg.mode),
            requested_mode=erepo_requested,
            planned_attempt=erepo_enabled,
            notes=["ClinGen ERepo is opt-in; curated external assertions are review-note only."],
        )
    )

    # ── Literature ─────────────────────────────────────────────────
    lit_enabled = options.get("include_literature", _DEFAULT_ENABLED)
    lit_check = check_literature_dependency(
        identity,
        explicit_query=options.get("search_query"),
        pmids=options.get("pmids") or [],
    )
    lit_cfg = data_sources_config.source("literature")
    lit_online = _use_online_literature(options)
    lit_requested = "online" if lit_online else _requested_mode(options, "use_online_pubmed", "literature")

    if lit_online:
        # Online path: uses search_and_summarize_literature.
        lit_dep_skip = not lit_check.satisfied
        lit_attempt = lit_enabled and not lit_dep_skip
        nodes.append(
            ProviderExecutionNode(
                node_key="search_and_summarize_literature",
                provider_name="literature",
                kind=ProviderNodeKind.LITERATURE,
                enabled=lit_enabled,
                dependency_check=lit_check,
                configured_mode=str(lit_cfg.mode),
                requested_mode=lit_requested,
                planned_attempt=lit_attempt,
                notes=["Online literature path: search + summarise. Dependency gate is enforced for online."],
            )
        )
        # Offline search node is present but not attempted in online mode.
        nodes.append(
            ProviderExecutionNode(
                node_key="search_literature_evidence",
                provider_name="literature",
                kind=ProviderNodeKind.LITERATURE,
                enabled=lit_enabled,
                dependency_check=lit_check,
                configured_mode=str(lit_cfg.mode),
                requested_mode=lit_requested,
                planned_attempt=False,  # online mode uses the summarise path instead
                notes=["Offline literature search; not attempted when online PubMed/LitVar is active."],
            )
        )
    else:
        # Offline path: uses search_literature_evidence.
        # Dependency gate is NOT enforced for offline.
        lit_attempt = lit_enabled
        nodes.append(
            ProviderExecutionNode(
                node_key="search_literature_evidence",
                provider_name="literature",
                kind=ProviderNodeKind.LITERATURE,
                enabled=lit_enabled,
                dependency_check=lit_check,
                configured_mode=str(lit_cfg.mode),
                requested_mode=lit_requested,
                planned_attempt=lit_attempt,
                notes=["Offline/mock literature search; dependency not gated in non-online paths."],
            )
        )
        # Summarise node is present but not attempted in offline mode.
        nodes.append(
            ProviderExecutionNode(
                node_key="search_and_summarize_literature",
                provider_name="literature",
                kind=ProviderNodeKind.LITERATURE,
                enabled=lit_enabled,
                dependency_check=lit_check,
                configured_mode=str(lit_cfg.mode),
                requested_mode=lit_requested,
                planned_attempt=False,  # offline mode uses the search-only path
                notes=["Online literature summarisation; not attempted when offline."],
            )
        )

    # ── provider_runtime ───────────────────────────────────────────
    nodes.append(
        ProviderExecutionNode(
            node_key="provider_runtime",
            provider_name="runtime",
            kind=ProviderNodeKind.RUNTIME_OBSERVABILITY,
            enabled=True,
            dependency_check=None,
            configured_mode="always",
            requested_mode="always",
            planned_attempt=True,
            notes=["ProviderRuntimeResult aggregation; always built by output_phase from step payloads."],
        )
    )

    # ── plan summary — computed explicitly per-branch, not inferred ──
    # dependency_unsatisfied: nodes on the ACTIVE branch whose check fails.
    dep_unsatisfied: list[str] = []
    # dependency_skip_planned: nodes the pipeline would actually skip
    # because the source is online AND the dependency gate is enforced.
    # Inactive sibling literature nodes must NOT appear here.
    dep_skip: list[str] = []

    # population
    if not gnomad_check.satisfied:
        dep_unsatisfied.append("query_population_frequency")
        if pop_online:
            dep_skip.append("query_population_frequency")

    # computational
    if not vep_check.satisfied:
        dep_unsatisfied.append("evaluate_computational_evidence")
        if comp_online and not has_inline_predictions:
            dep_skip.append("evaluate_computational_evidence")

    # clinvar
    if not clinvar_check.satisfied:
        dep_unsatisfied.append("query_clinvar")
        if clinvar_online:
            dep_skip.append("query_clinvar")

    # literature — only the active-branch node can be a dep-skip
    if not lit_check.satisfied:
        if lit_online:
            dep_unsatisfied.append("search_and_summarize_literature")
            dep_skip.append("search_and_summarize_literature")
        else:
            dep_unsatisfied.append("search_literature_evidence")
            # offline literature never dependency-skips; dep gate not enforced

    attempted = [node.node_key for node in nodes if node.planned_attempt]
    enabled_count = sum(1 for node in nodes if node.enabled)
    kind_counts: dict[str, int] = {}
    for node in nodes:
        kind_counts[str(node.kind)] = kind_counts.get(str(node.kind), 0) + 1

    return ProviderExecutionPlan(
        provider_identity=_copy_identity(identity),
        nodes=nodes,
        dependency_unsatisfied=dep_unsatisfied,
        dependency_skip_planned=dep_skip,
        dependency_skipped=list(dep_skip),  # legacy alias
        attempted=attempted,
        summary={
            "total_nodes": len(nodes),
            "enabled_count": enabled_count,
            "dependency_unsatisfied_count": len(dep_unsatisfied),
            "dependency_skip_planned_count": len(dep_skip),
            "attempted_count": len(attempted),
            "by_kind": kind_counts,
            "dependency_unsatisfied_nodes": dep_unsatisfied,
            "dependency_skip_planned_nodes": dep_skip,
            "attempted_nodes": attempted,
        },
    )


# ── helpers ──────────────────────────────────────────────────────────


def _copy_identity(identity: VariantIdentity) -> VariantIdentity:
    """Return a snapshot copy so mutations to the original don't leak into the plan."""
    return VariantIdentity.model_validate(identity.model_dump(mode="json"))


def _online_source(data_sources_config: DataSourcesConfig, source_name: str) -> bool:
    """Mirrors ``evidence_phase._online_source``."""
    source = data_sources_config.source(source_name)
    return source.mode == ProviderMode.ONLINE and bool(source.online_enabled)


def _use_online_literature(options: dict[str, Any]) -> bool:
    """Mirrors ``evidence_phase._use_online_literature``."""
    return bool(options.get("use_online_pubmed") or options.get("use_online_litvar"))


def _requested_mode(options: dict[str, Any], online_flag: str, source_name: str) -> str:
    if options.get(online_flag):
        return "online"
    source_override = (
        (options.get("data_sources") or {}).get("sources", {}).get(source_name)
        if isinstance(options.get("data_sources"), dict)
        else None
    )
    if isinstance(source_override, dict) and source_override.get("mode"):
        return str(source_override["mode"])
    return "default"
