"""79A-3A — Provider orchestrator contract scaffold tests (post-review)."""

from __future__ import annotations

from variant_pathogenicity_rater.data_sources.config import (
    DataSourceConfig,
    DataSourcesConfig,
    ProviderMode,
)
from variant_pathogenicity_rater.providers import (
    ProviderDependencyStatus,
    ProviderExecutionNode,
    ProviderExecutionPlan,
    ProviderNodeKind,
    VariantIdentity,
    build_provider_execution_plan,
    dependency_check_from_plan,
    provider_node_from_plan,
)
from variant_pathogenicity_rater.schemas.common import SchemaModel


def _identity(**overrides: object) -> VariantIdentity:
    kwargs: dict[str, object] = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "genome_build": "GRCh38",
        "chrom": "17",
        "pos": 43124027,
        "ref": "CA",
        "alt": "C",
    }
    kwargs.update(overrides)
    return VariantIdentity(**{k: v for k, v in kwargs.items() if v is not None})


def _mock_config() -> DataSourcesConfig:
    return DataSourcesConfig(
        sources={
            "clinvar": DataSourceConfig(name="clinvar", mode=ProviderMode.MOCK),
            "population": DataSourceConfig(name="population", mode=ProviderMode.MOCK),
            "computational": DataSourceConfig(name="computational", mode=ProviderMode.MOCK),
            "literature": DataSourceConfig(name="literature", mode=ProviderMode.MOCK),
            "clingen_erepo": DataSourceConfig(name="clingen_erepo", mode=ProviderMode.MOCK),
        }
    )


def _online_config() -> DataSourcesConfig:
    return DataSourcesConfig(
        sources={
            "clinvar": DataSourceConfig(name="clinvar", mode=ProviderMode.ONLINE, online_enabled=True),
            "population": DataSourceConfig(name="population", mode=ProviderMode.ONLINE, online_enabled=True),
            "computational": DataSourceConfig(name="computational", mode=ProviderMode.ONLINE, online_enabled=True),
            "literature": DataSourceConfig(name="literature", mode=ProviderMode.ONLINE, online_enabled=True),
            "clingen_erepo": DataSourceConfig(name="clingen_erepo", mode=ProviderMode.MOCK),
        }
    )


# ── Plan structure ──────────────────────────────────────────────────


def test_build_plan_has_all_expected_nodes() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    keys = {node.node_key for node in plan.nodes}
    assert keys == {
        "provider_identity",
        "query_population_frequency",
        "evaluate_computational_evidence",
        "query_clinvar",
        "query_clingen_erepo",
        "search_literature_evidence",
        "search_and_summarize_literature",
        "provider_runtime",
    }


def test_plan_version_is_stable() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    assert plan.plan_version == "79A-3A-v1"


# ── enabled / include flags ──────────────────────────────────────────


def test_all_runtime_providers_enabled_by_default() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    for node in plan.nodes:
        if node.node_key in ("provider_identity", "provider_runtime"):
            assert node.enabled is True
        elif node.node_key == "query_clingen_erepo":
            assert node.enabled is False  # opt-in
        else:
            assert node.enabled is True, f"{node.node_key} should be enabled by default"


def test_include_population_false_disables_node() -> None:
    plan = build_provider_execution_plan(_identity(), {"include_population": False}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "query_population_frequency")
    assert node.enabled is False
    assert node.planned_attempt is False


def test_include_computational_false_disables_node() -> None:
    plan = build_provider_execution_plan(_identity(), {"include_computational": False}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "evaluate_computational_evidence")
    assert node.enabled is False
    assert node.planned_attempt is False


def test_include_clinvar_false_disables_node() -> None:
    plan = build_provider_execution_plan(_identity(), {"include_clinvar": False}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "query_clinvar")
    assert node.enabled is False
    assert node.planned_attempt is False


def test_include_literature_false_disables_both_lit_nodes() -> None:
    plan = build_provider_execution_plan(_identity(), {"include_literature": False}, _mock_config())
    for key in ("search_literature_evidence", "search_and_summarize_literature"):
        node = next(n for n in plan.nodes if n.node_key == key)
        assert node.enabled is False, key
        assert node.planned_attempt is False, key


# ── planned_attempt: mock/local always attempts (unless disabled) ────


def test_mock_population_with_valid_identity_attempts() -> None:
    """Mock population with valid gnomAD identity → planned_attempt=true."""
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "query_population_frequency")
    assert node.enabled is True
    assert node.planned_attempt is True


def test_mock_population_with_invalid_gnomad_still_attempts() -> None:
    """Invalid gnomAD in mock mode still attempts — dependency gate only enforced online."""
    identity = _identity(chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "query_population_frequency")
    assert node.dependency_check is not None
    assert node.dependency_check.satisfied is False
    assert node.planned_attempt is True  # mock path — no gate


def test_mock_computational_with_invalid_vep_still_attempts() -> None:
    """Invalid VEP identity in mock mode still attempts (mock/local inline path)."""
    identity = _identity(chrom=None, pos=None, hgvs_c=None)
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "evaluate_computational_evidence")
    assert node.dependency_check is not None
    assert node.dependency_check.satisfied is False
    assert node.planned_attempt is True  # mock/local/inline path


def test_mock_clinvar_with_invalid_identity_still_attempts() -> None:
    identity = _identity(gene=None, hgvs_c=None, chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "query_clinvar")
    assert node.dependency_check is not None
    assert node.dependency_check.satisfied is False
    assert node.planned_attempt is True  # mock path — no gate


# ── dependency_unsatisfied vs dependency_skip_planned ───────────────


def test_invalid_gnomad_in_online_is_dep_skip_planned() -> None:
    identity = _identity(chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _online_config())
    node = next(n for n in plan.nodes if n.node_key == "query_population_frequency")
    assert node.planned_attempt is False
    assert "query_population_frequency" in plan.dependency_unsatisfied
    assert "query_population_frequency" in plan.dependency_skip_planned
    assert plan.dependency_skipped == plan.dependency_skip_planned


def test_invalid_gnomad_in_mock_is_unsatisfied_but_not_dep_skip_planned() -> None:
    identity = _identity(chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    assert "query_population_frequency" in plan.dependency_unsatisfied
    assert "query_population_frequency" not in plan.dependency_skip_planned
    assert "query_population_frequency" in plan.attempted


def test_invalid_clinvar_in_online_is_dep_skip_planned() -> None:
    identity = _identity(gene=None, hgvs_c=None, chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _online_config())
    assert "query_clinvar" in plan.dependency_unsatisfied
    assert "query_clinvar" in plan.dependency_skip_planned
    node = next(n for n in plan.nodes if n.node_key == "query_clinvar")
    assert node.planned_attempt is False


# ── computational: inline predictions bypass the online gate ─────────


def test_computational_inline_predictions_bypass_online_dep_gate() -> None:
    """Inline computational_predictions with invalid VEP → still attempts."""
    identity = _identity(chrom=None, pos=None, hgvs_c=None)
    options = {"computational_predictions": [{"method": "REVEL", "score": 0.9, "prediction": "deleterious"}]}
    plan = build_provider_execution_plan(identity, options, _online_config())
    node = next(n for n in plan.nodes if n.node_key == "evaluate_computational_evidence")
    assert node.dependency_check is not None
    assert node.dependency_check.satisfied is False
    assert node.planned_attempt is True  # inline predictions bypass gate


def test_computational_no_inline_online_invalid_vep_is_dep_skip() -> None:
    """No inline predictions + online + invalid VEP → dep-skip."""
    identity = _identity(chrom=None, pos=None, hgvs_c=None)
    plan = build_provider_execution_plan(identity, {}, _online_config())
    node = next(n for n in plan.nodes if n.node_key == "evaluate_computational_evidence")
    assert node.planned_attempt is False
    assert "evaluate_computational_evidence" in plan.dependency_skip_planned


# ── literature routing ──────────────────────────────────────────────


def test_offline_literature_plans_search_only() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    search = next(n for n in plan.nodes if n.node_key == "search_literature_evidence")
    summarise = next(n for n in plan.nodes if n.node_key == "search_and_summarize_literature")
    assert search.planned_attempt is True
    assert summarise.planned_attempt is False


def test_online_pubmed_plans_summarise_only() -> None:
    plan = build_provider_execution_plan(_identity(), {"use_online_pubmed": True}, _online_config())
    search = next(n for n in plan.nodes if n.node_key == "search_literature_evidence")
    summarise = next(n for n in plan.nodes if n.node_key == "search_and_summarize_literature")
    assert search.planned_attempt is False
    assert summarise.planned_attempt is True


def test_online_litvar_plans_summarise_only() -> None:
    plan = build_provider_execution_plan(_identity(), {"use_online_litvar": True}, _online_config())
    search = next(n for n in plan.nodes if n.node_key == "search_literature_evidence")
    summarise = next(n for n in plan.nodes if n.node_key == "search_and_summarize_literature")
    assert search.planned_attempt is False
    assert summarise.planned_attempt is True


def test_online_literature_missing_dependency_is_dep_skip_planned() -> None:
    identity = _identity(gene=None, hgvs_c=None, chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {"use_online_pubmed": True}, _online_config())
    # Active branch node is a dep-skip.
    assert "search_and_summarize_literature" in plan.dependency_unsatisfied
    assert "search_and_summarize_literature" in plan.dependency_skip_planned
    node = next(n for n in plan.nodes if n.node_key == "search_and_summarize_literature")
    assert node.planned_attempt is False
    # Inactive sibling must NOT be in dep-skip.
    assert "search_literature_evidence" not in plan.dependency_skip_planned
    assert "search_literature_evidence" not in plan.dependency_unsatisfied


def test_offline_literature_never_dep_skip_planned() -> None:
    identity = _identity(gene=None, hgvs_c=None, chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    search = next(n for n in plan.nodes if n.node_key == "search_literature_evidence")
    assert search.dependency_check is not None
    assert search.dependency_check.satisfied is False
    assert search.planned_attempt is True  # offline — no gate
    assert "search_literature_evidence" in plan.dependency_unsatisfied
    assert "search_literature_evidence" not in plan.dependency_skip_planned
    # Inactive sibling must NOT be in dep-skip.
    assert "search_and_summarize_literature" not in plan.dependency_skip_planned
    assert "search_and_summarize_literature" not in plan.dependency_unsatisfied


def test_online_valid_literature_only_summarise_attempted() -> None:
    """Online valid literature: only summarise attempted, search not attempted
    and NOT in dependency_skip_planned."""
    plan = build_provider_execution_plan(_identity(), {"use_online_pubmed": True}, _online_config())
    search = next(n for n in plan.nodes if n.node_key == "search_literature_evidence")
    summarise = next(n for n in plan.nodes if n.node_key == "search_and_summarize_literature")
    assert summarise.planned_attempt is True
    assert search.planned_attempt is False
    # Inactive sibling (search) is NOT a dependency skip — it's an inactive branch.
    assert "search_literature_evidence" not in plan.dependency_skip_planned
    assert "search_literature_evidence" not in plan.dependency_unsatisfied
    # Active node is not a dep-skip (dependency is satisfied).
    assert "search_and_summarize_literature" not in plan.dependency_skip_planned
    assert "search_and_summarize_literature" not in plan.dependency_unsatisfied


def test_offline_missing_lit_dependency_inactive_sibling_not_dep_skip() -> None:
    """Offline with missing literature dependency: search attempted,
    summarise not attempted, and NEITHER is in dependency_skip_planned."""
    identity = _identity(gene=None, hgvs_c=None, chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    search = next(n for n in plan.nodes if n.node_key == "search_literature_evidence")
    summarise = next(n for n in plan.nodes if n.node_key == "search_and_summarize_literature")
    assert search.planned_attempt is True
    assert summarise.planned_attempt is False
    # The inactive summarise node is NOT a dependency skip — offline never gates.
    assert "search_and_summarize_literature" not in plan.dependency_skip_planned
    assert "search_literature_evidence" not in plan.dependency_skip_planned


# ── summary consistency ─────────────────────────────────────────────


def test_summary_counts_are_consistent() -> None:
    identity = _identity(chrom=None, pos=None)  # invalid gnomAD
    plan = build_provider_execution_plan(identity, {}, _online_config())
    assert plan.summary["total_nodes"] == len(plan.nodes)
    assert plan.summary["enabled_count"] == sum(1 for n in plan.nodes if n.enabled)
    assert plan.summary["dependency_unsatisfied_count"] == len(plan.dependency_unsatisfied)
    assert plan.summary["dependency_skip_planned_count"] == len(plan.dependency_skip_planned)
    assert plan.summary["attempted_count"] == len(plan.attempted)
    assert set(plan.summary["dependency_unsatisfied_nodes"]) == set(plan.dependency_unsatisfied)
    assert set(plan.summary["dependency_skip_planned_nodes"]) == set(plan.dependency_skip_planned)
    assert set(plan.summary["attempted_nodes"]) == set(plan.attempted)
    # Exact match, not just set equality.
    assert plan.summary["dependency_skip_planned_nodes"] == list(plan.dependency_skip_planned)
    assert plan.summary["attempted_nodes"] == list(plan.attempted)


def test_summary_dep_skip_planned_nodes_exactly_matches_plan() -> None:
    """dependency_skip_planned_nodes in summary must be the exact list,
    not a different order or superset."""
    identity = _identity(chrom=None, pos=None)
    plan = build_provider_execution_plan(identity, {"use_online_pubmed": True}, _online_config())
    assert plan.summary["dependency_skip_planned_nodes"] == plan.dependency_skip_planned


# ── Schema / serialisation ──────────────────────────────────────────


def test_execution_plan_is_json_serializable() -> None:
    import json
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    payload = plan.model_dump(mode="json")
    serialized = json.dumps(payload)
    round_tripped = json.loads(serialized)
    assert round_tripped["plan_version"] == "79A-3A-v1"
    assert "dependency_unsatisfied" in round_tripped
    assert "dependency_skip_planned" in round_tripped
    assert "dependency_skipped" in round_tripped


def test_execution_plan_is_a_schema_model() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    assert isinstance(plan, SchemaModel)


# ── Side-effect isolation ───────────────────────────────────────────


def test_build_plan_has_no_side_effect_on_identity() -> None:
    identity = _identity()
    original_gene = identity.gene
    build_provider_execution_plan(identity, {}, _mock_config())
    assert identity.gene == original_gene


def test_plan_provider_identity_is_a_copy() -> None:
    identity = _identity()
    plan = build_provider_execution_plan(identity, {}, _mock_config())
    identity.gene = "MUTATED"
    assert plan.provider_identity is not None
    assert plan.provider_identity.gene == "BRCA1"


# ── Edge cases ──────────────────────────────────────────────────────


def test_empty_options_still_build_plan() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    assert len(plan.nodes) == 8
    assert plan.plan_version == "79A-3A-v1"


def test_clingen_erepo_not_attempted_by_default() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    node = next(n for n in plan.nodes if n.node_key == "query_clingen_erepo")
    assert node.enabled is False
    assert node.planned_attempt is False


def test_clingen_erepo_attempted_when_opt_in() -> None:
    plan = build_provider_execution_plan(
        _identity(), {"include_clingen_erepo": True}, _mock_config()
    )
    node = next(n for n in plan.nodes if n.node_key == "query_clingen_erepo")
    assert node.enabled is True
    assert node.planned_attempt is True


def test_valid_gnomad_online_with_flag_attempts() -> None:
    plan = build_provider_execution_plan(
        _identity(), {"use_online_gnomad": True}, _online_config()
    )
    node = next(n for n in plan.nodes if n.node_key == "query_population_frequency")
    assert node.dependency_check is not None
    assert node.dependency_check.satisfied is True
    assert node.planned_attempt is True
    assert "query_population_frequency" in plan.attempted
    assert "query_population_frequency" not in plan.dependency_skip_planned


# ── 79A-3D: plan accessor helpers ────────────────────────────────────


def test_provider_node_from_plan_returns_node_for_valid_key() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    node = provider_node_from_plan(plan, "query_clinvar")
    assert node is not None
    assert node.node_key == "query_clinvar"
    assert node.provider_name == "clinvar"


def test_provider_node_from_plan_returns_none_for_missing_key() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    assert provider_node_from_plan(plan, "nonexistent") is None


def test_provider_node_from_plan_returns_none_for_none_plan() -> None:
    assert provider_node_from_plan(None, "query_clinvar") is None


def test_dependency_check_from_plan_returns_check_for_valid_key() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    check = dependency_check_from_plan(plan, "query_population_frequency")
    assert check is not None
    assert check.provider_name == "gnomad"
    assert check.satisfied is True


def test_dependency_check_from_plan_returns_none_for_node_without_check() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    assert dependency_check_from_plan(plan, "provider_identity") is None


def test_dependency_check_from_plan_returns_none_for_none_plan() -> None:
    assert dependency_check_from_plan(None, "query_population_frequency") is None


def test_dependency_check_from_plan_returns_none_for_missing_key() -> None:
    plan = build_provider_execution_plan(_identity(), {}, _mock_config())
    assert dependency_check_from_plan(plan, "nonexistent") is None


def test_invalid_gnomad_online_identity_is_dep_unsatisfied_and_dep_skip() -> None:
    """Invalid gnomAD identity with online source → dependency_unsatisfied AND
    dependency_skip_planned for query_population_frequency."""
    identity = _identity(chrom=None, pos=None)  # no coordinate → invalid gnomAD
    plan = build_provider_execution_plan(identity, {"use_online_gnomad": True}, _online_config())

    assert "query_population_frequency" in plan.dependency_unsatisfied
    assert "query_population_frequency" in plan.dependency_skip_planned
    node = provider_node_from_plan(plan, "query_population_frequency")
    assert node is not None
    assert node.planned_attempt is False
    assert node.dependency_check is not None
    assert node.dependency_check.satisfied is False
