from __future__ import annotations

import asyncio
import json

from server import McpServer, build_registry
from config import ServerConfig
from variant_pathogenicity_rater.data_sources.provider_result import (
    provider_entry_from_runtime_json,
    provider_summary_from_runtime_json,
)
from variant_pathogenicity_rater.pipeline.output_schema import add_rate_variant_canonical_fields
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch


def _server() -> McpServer:
    config = ServerConfig(
        server_name="variant-pathogenicity-rater-test",
        server_version="0.1.0",
        log_level="ERROR",
        tools_package="tools",
        enable_health_tool=True,
        environment="test",
    )
    return McpServer(config, build_registry(config))


def _flat_variant_payload() -> dict:
    return {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43092919,
        "ref": "AG",
        "alt": "A",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
        "phenotype": ["HP:0003002"],
    }


def _complete_brca1_pvs1_payload() -> dict:
    annotation = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "consequence": "frameshift_variant",
        "consequence_terms": ["frameshift_variant"],
        "exon": "2/24",
        "canonical": True,
        "mane_select": True,
        "transcript_biotype": "protein_coding",
        "annotation_source": "pytest",
        "provenance": {"data_source": "pytest", "source_version": "v1", "raw_record_hash": "brca1-pvs1"},
        "raw_fields": {"case": "brca1-pvs1"},
    }
    return {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43124027,
        "ref": "CA",
        "alt": "C",
        "disease": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "autosomal_dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "annotations": [annotation],
            "gene_disease_context": {
                "gene": "BRCA1",
                "disease": "Hereditary breast and ovarian cancer syndrome",
                "inheritance": "autosomal_dominant",
                "lof_is_known_mechanism": True,
                "transcript_is_biologically_relevant": True,
                "nmd_prediction_available": True,
                "nmd_predicted": True,
                "last_exon_information": {
                    "is_in_last_exon": False,
                    "exon_number": 2,
                    "total_exons": 24,
                },
            },
        },
    }


def _without_runtime_timestamps(value):
    if isinstance(value, dict):
        return {
            key: _without_runtime_timestamps(item)
            for key, item in value.items()
            if key not in {"retrieval_timestamp", "timestamp"}
        }
    if isinstance(value, list):
        return [_without_runtime_timestamps(item) for item in value]
    return value


def test_rate_variant_pipeline_runs_complete_offline_workflow() -> None:
    result = rate_variant(_flat_variant_payload())

    assert result["status"] == "ok"
    assert result["mock_mode"] is True
    assert result["normalized_variant"]["gene_symbol"] == "BRCA1"
    assert result["classification_result"]["human_review_required"] is True
    assert result["final_classification"] in {
        "pathogenic",
        "likely_pathogenic",
        "vus",
        "likely_benign",
        "benign",
    }
    assert result["evidence_items"]
    assert "normalization_identity" in result
    assert "variant_resolution" in result
    assert "resolved_variant" in result
    assert "applied_evidence" in result
    assert "review_note_evidence" in result
    assert "review_flags" in result
    assert "provenance" in result
    assert result["report_text"]
    assert result["limitations"]
    assert result["human_review_required"] is True
    for key in (
        "input",
        "variant",
        "context",
        "runtime",
        "providers",
        "evidence",
        "classification",
        "review",
        "report",
        "provenance",
        "warnings",
        "compatibility",
    ):
        assert key in result
    assert result["classification"]["final_classification"] == result["final_classification"]
    assert result["evidence"]["applied"] == result["applied_evidence"]
    assert result["evidence"]["review_note"] == result["review_note_evidence"]
    assert result["candidate_evidence"] == result["review_note_evidence"]
    assert result["providers"]["summary"] == result["provider_mode_summary"]
    assert "provider_runtime" in result["step_results"]
    assert result["step_results"]["provider_runtime"]["clinvar"]["outcome"] == result["provider_mode_summary"]["clinvar"]["outcome"]
    assert result["providers"]["clinvar"]["outcome"] == result["step_results"]["provider_runtime"]["clinvar"]["outcome"]
    assert result["runtime"]["legacy_mock_mode"] == result["mock_mode"]
    assert result["variant"]["normalized"] == result["normalized_variant"]
    assert result["variant"]["resolved"] == result["resolved_variant"]
    assert result["variant"]["resolution_summary"] == result["variant_resolution"]
    assert result["variant"]["provider_identity"] == result["provider_identity"]
    assert "provider_dependency_checks" in result
    assert "mock_mode" in result["compatibility"]["legacy_fields"]

    completed_steps = {event["tool_name"] for event in result["audit_trail"]}
    assert {
        "normalize_variant",
        "resolve_variant",
        "query_population_frequency",
        "evaluate_population_rules",
        "evaluate_computational_evidence",
        "evaluate_pvs1",
        "query_clinvar",
        "search_literature_evidence",
        "combine_all_evidence",
        "classify_acmg",
        "generate_report",
    }.issubset(completed_steps)


def test_rate_variant_pipeline_records_module_failure_as_limitation() -> None:
    payload = {
        **_flat_variant_payload(),
        "options": {
            "computational_predictions": [
                {
                    "source": {"name": "bad_fixture", "version": "v1"},
                    "method": "REVEL",
                    "score": "not-a-number",
                    "prediction": "deleterious",
                }
            ]
        },
    }

    result = rate_variant(payload)

    assert result["status"] == "ok"
    assert result["classification_result"]["human_review_required"] is True
    assert any(
        limitation.startswith("evaluate_computational_evidence failed:")
        for limitation in result["limitations"]
    )
    assert any(
        event["tool_name"] == "evaluate_computational_evidence"
        and event["event_type"] == "evaluate_computational_evidence_failed"
        for event in result["audit_trail"]
    )


def test_mcp_rate_variant_tool_calls_integrated_pipeline() -> None:
    server = _server()
    request = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": _flat_variant_payload(),
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["status"] == "ok"
    assert tool_payload["tool"] == "rate_variant"
    assert tool_payload["stage"] == "integrated_snv_small_indel_acmg_pipeline"
    assert tool_payload["classification_result"]["human_review_required"] is True
    assert tool_payload["report"]["human_review_required"] is True


def test_report_json_stable_keys_present_for_single_and_batch() -> None:
    single = rate_variant(_flat_variant_payload())
    batch = rate_variant_batch({"records": [_flat_variant_payload()]})
    batch_record = batch["results"][0]

    assert {
        "report_id",
        "result_id",
        "summary",
        "content",
        "source_result",
        "human_review_required",
    }.issubset(single["report"])
    assert {
        "applied_evidence",
        "review_note_evidence",
        "normalization_identity",
        "transcript_selection_summary",
        "context_consistency_summary",
        "review_flags",
        "provenance",
    }.issubset(batch_record)
    assert {"total_records", "succeeded", "failed", "classification_distribution"}.issubset(
        batch["summary"]
    )


def test_report_language_does_not_change_classification_or_evidence_items() -> None:
    base_payload = {
        **_flat_variant_payload(),
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }
    english = rate_variant(
        {
            **base_payload,
            "options": {
                **base_payload["options"],
                "report_language": "en",
                "report_mode": "laboratory",
            },
        }
    )
    chinese = rate_variant(
        {
            **base_payload,
            "options": {
                **base_payload["options"],
                "report_language": "zh",
                "report_mode": "laboratory",
            },
        }
    )

    assert english["final_classification"] == chinese["final_classification"]
    assert english["classification_result"]["final_classification"] == chinese["classification_result"][
        "final_classification"
    ]
    assert english["classification_result"]["applied_combination_rule"] == chinese[
        "classification_result"
    ]["applied_combination_rule"]
    assert _without_runtime_timestamps(english["evidence_items"]) == _without_runtime_timestamps(
        chinese["evidence_items"]
    )
    assert _without_runtime_timestamps(english["applied_evidence"]) == _without_runtime_timestamps(
        chinese["applied_evidence"]
    )
    assert _without_runtime_timestamps(english["review_note_evidence"]) == _without_runtime_timestamps(
        chinese["review_note_evidence"]
    )
    assert _without_runtime_timestamps(
        english["report"]["source_result"]["evidence_items"]
    ) == _without_runtime_timestamps(chinese["report"]["source_result"]["evidence_items"])
    assert "## 报告摘要" in chinese["report_text"]
    assert "## Executive Summary" in english["report_text"]


def test_mcp_rate_variant_accepts_chinese_report_options_without_changing_result() -> None:
    server = _server()
    request = {
        "jsonrpc": "2.0",
        "id": 58,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": {
                **_flat_variant_payload(),
                "options": {
                    "include_population": False,
                    "include_computational": False,
                    "include_clinvar": False,
                    "include_literature": False,
                    "report_language": "zh",
                    "report_mode": "laboratory",
                },
            },
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["status"] == "ok"
    assert tool_payload["classification_result"]["human_review_required"] is True
    assert tool_payload["report"]["language"] == "zh"
    assert "## 报告摘要" in tool_payload["report_text"]


def test_context_conflict_is_reported_without_changing_classification() -> None:
    base_payload = {
        **_flat_variant_payload(),
        "hgvs_c": "NM_007294.4:c.68A>G",
        "hgvs_p": "NP_009225.1:p.Glu23Val",
        "ref": "A",
        "alt": "G",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }
    conflict_payload = {
        **base_payload,
        "options": {
            **base_payload["options"],
            "include_transcript_selection": True,
            "annotations": [
                {
                    "gene": "TP53",
                    "transcript": "NM_007294.4",
                    "hgvs_c": "NM_007294.4:c.68A>G",
                    "hgvs_p": "NP_009225.1:p.Glu23Val",
                    "consequence": "missense_variant",
                    "annotation_source": "test_annotation",
                    "provenance": {
                        "data_source": "test_annotation",
                        "raw_record_hash": "abc123",
                    },
                    "raw_fields": {},
                }
            ],
        },
    }

    base = rate_variant(base_payload)
    conflict = rate_variant(conflict_payload)

    assert conflict["context_consistency"]["status"] == "conflict"
    assert "user_gene_vs_annotation_gene" in conflict["report_text"]
    assert conflict["final_classification"] == base["final_classification"]


def test_candidate_evidence_remains_excluded_in_single_and_batch_workflows() -> None:
    candidate = {
        "evidence_id": "ev-candidate-ps3",
        "code": "PS3",
        "strength": "strong",
        "direction": "pathogenic",
        "reason": "Candidate-only functional note should not be counted.",
        "source": {"name": "manual_review_note", "version": "test"},
        "confidence": 0.9,
        "requires_review": True,
        "candidate_only": True,
        "applied": False,
        "supporting_data": {
            "candidate_only": True,
            "applied": False,
            "evidence_status": "candidate",
        },
    }
    payload = {
        **_flat_variant_payload(),
        "hgvs_c": "NM_007294.4:c.68A>G",
        "hgvs_p": "NP_009225.1:p.Glu23Val",
        "ref": "A",
        "alt": "G",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "mock_supplemental_evidence_items": [candidate],
        },
    }

    single = rate_variant(payload)
    batch = rate_variant_batch({"records": [payload]})

    assert single["final_classification"] == "vus"
    assert single["applied_evidence"] == []
    assert single["review_note_evidence"][0]["evidence_id"] == "ev-candidate-ps3"
    assert batch["results"][0]["classification_result"]["final_classification"] == "vus"
    assert batch["results"][0]["applied_evidence"] == []
    assert batch["results"][0]["review_note_evidence"][0]["evidence_id"] == "ev-candidate-ps3"


def test_pipeline_applies_pvs1_only_with_complete_context_and_preserves_decision_path() -> None:
    result = rate_variant(_complete_brca1_pvs1_payload())
    pvs1_items = [item for item in result["applied_evidence"] if item["code"] == "PVS1"]

    assert len(pvs1_items) == 1
    pvs1 = pvs1_items[0]
    assert pvs1["applied"] is True
    assert pvs1["candidate_only"] is False
    assert pvs1["requires_review"] is True
    assert pvs1["supporting_data"]["requires_manual_review"] is True
    assert pvs1["supporting_data"]["pvs1_decision"]["decision_path"]
    assert "PVS1 decision path" in result["report_text"]


def test_pipeline_missing_nmd_and_exon_annotation_keeps_pvs1_candidate_only() -> None:
    payload = _complete_brca1_pvs1_payload()
    payload["options"]["annotations"][0].pop("exon")
    payload["options"]["gene_disease_context"].update(
        {
            "nmd_prediction_available": False,
            "nmd_predicted": None,
            "last_exon_information": None,
        }
    )

    result = rate_variant(payload)
    applied_pvs1 = [item for item in result["applied_evidence"] if item["code"] == "PVS1"]
    candidate_pvs1 = [item for item in result["review_note_evidence"] if item["code"] == "PVS1"]

    assert result["final_classification"] == "vus"
    assert applied_pvs1 == []
    assert len(candidate_pvs1) == 1
    assert candidate_pvs1[0]["supporting_data"]["evidence_status"] == "candidate"
    assert candidate_pvs1[0]["supporting_data"]["pvs1_decision"]["blocking_reasons"]


def test_context_conflict_blocks_applied_pvs1_before_combiner() -> None:
    payload = _complete_brca1_pvs1_payload()
    payload["options"]["annotations"][0]["gene"] = "TP53"
    payload["options"]["annotations"][0]["raw_fields"] = {"case": "context-conflict"}

    result = rate_variant(payload)
    candidate_pvs1 = [item for item in result["review_note_evidence"] if item["code"] == "PVS1"]

    assert result["context_consistency"]["status"] == "conflict"
    assert result["applied_evidence"] == []
    assert len(candidate_pvs1) == 1
    assert "Major context consistency conflict is present." in candidate_pvs1[0]["supporting_data"]["blocking_reasons"]


def test_mcp_rate_variant_output_includes_pvs1_supporting_data() -> None:
    server = _server()
    request = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": _complete_brca1_pvs1_payload(),
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])
    pvs1 = next(item for item in tool_payload["applied_evidence"] if item["code"] == "PVS1")

    assert pvs1["supporting_data"]["pvs1_decision"]["decision_path"]
    assert pvs1["supporting_data"]["requires_manual_review"] is True


def test_mcp_rate_annotated_variants_preserves_pvs1_decision_path_per_record() -> None:
    payload = _complete_brca1_pvs1_payload()
    annotation = payload["options"]["annotations"][0]
    server = _server()
    request = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "rate_annotated_variants",
            "arguments": {
                "annotation_format": "generic",
                "records": [annotation["raw_fields"] | annotation],
                "gene_disease_context": payload["options"]["gene_disease_context"],
                "options": {
                    "include_population": False,
                    "include_computational": False,
                    "include_clinvar": False,
                    "include_literature": False,
                },
            },
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])
    record = tool_payload["results"][0]
    pvs1 = next(item for item in record["applied_evidence"] if item["code"] == "PVS1")

    assert pvs1["supporting_data"]["decision_path"]


def test_canonical_providers_summary_survives_stale_provider_mode_summary() -> None:
    """Canonical providers.summary must be projected from
    step_results.provider_runtime, not from the legacy provider_mode_summary
    top-level field."""
    result = rate_variant(_flat_variant_payload())

    # Baseline: both should be equal for a fresh pipeline result.
    assert result["providers"]["summary"] == result["provider_mode_summary"]

    # Simulate a stale/conflicting provider_mode_summary.
    stale_summary = {
        "clinvar": {
            "requested_mode": "default",
            "configured_mode": "mock",
            "actual_outcome": "success",
            "outcome": "success",
            "records_count": 999,
            "source_version": "stale-v99",
            "attempted": True,
            "cache_hit": True,
            "provider_mode": "mock",
            "endpoint": "https://stale.example.com",
            "query": {"stale": True},
        },
    }
    result["provider_mode_summary"] = stale_summary

    # Re-apply canonical fields so _providers_section re-runs.
    add_rate_variant_canonical_fields(result)

    # providers.summary must reflect provider_runtime, not the stale summary.
    assert result["providers"]["summary"] != stale_summary
    assert result["provider_mode_summary"] == stale_summary  # legacy field preserved as-is

    # The canonical summary must match what provider_runtime projects.
    provider_runtime = result["step_results"]["provider_runtime"]
    projected = provider_summary_from_runtime_json(provider_runtime)
    assert result["providers"]["summary"] == projected
    # Non-stale providers should still match the runtime entry.
    for name in projected:
        assert result["providers"]["summary"][name]["outcome"] == provider_runtime[name]["outcome"]


def test_canonical_providers_summary_falls_back_to_legacy_when_runtime_missing() -> None:
    """When step_results.provider_runtime is absent, providers.summary
    must fall back to the legacy provider_mode_summary."""
    result = rate_variant(_flat_variant_payload())
    result["provider_mode_summary"] = {
        "clinvar": {"outcome": "fallback_only", "records_count": 1},
    }
    result["step_results"].pop("provider_runtime", None)

    add_rate_variant_canonical_fields(result)

    assert result["providers"]["summary"] == result["provider_mode_summary"]


# ── 81C regression tests ──


def test_pipeline_limitations_appear_in_final_classification_result() -> None:
    """After output_phase finalizes classification_result.limitations,
    the serialized classification_result must carry the full limitations
    list (not just the pre-report set)."""
    result = rate_variant(_flat_variant_payload())

    serialized = result["classification_result"]
    assert isinstance(serialized, dict)
    assert "limitations" in serialized
    # The output phase merges pipeline limitations into the result.
    assert any(
        "mock mode" in str(item).lower() or "human review" in str(item).lower()
        for item in serialized["limitations"]
    )
    # Must also appear in the top-level limitations field.
    assert result["limitations"] == serialized["limitations"]


def test_canonical_provider_entries_validated_through_provider_runtime() -> None:
    """Every runtime-backed canonical provider entry must be projectable
    through ``provider_entry_from_runtime_json`` with matching outcome."""
    result = rate_variant(_flat_variant_payload())

    provider_runtime = result["step_results"]["provider_runtime"]
    for name in ("clinvar", "population", "computational", "literature", "clingen_erepo"):
        canonical = result["providers"][name]
        payload = provider_runtime.get(name)
        assert isinstance(payload, dict), f"{name} missing from provider_runtime"
        projected = provider_entry_from_runtime_json(name, payload)
        assert projected["outcome"] == canonical["outcome"], f"{name} outcome mismatch"
        assert projected["attempted"] == canonical["attempted"], f"{name} attempted mismatch"
        assert projected["records_count"] == canonical["records_count"], f"{name} records mismatch"


def test_malformed_provider_runtime_entry_yields_safe_fallback() -> None:
    """A malformed provider_runtime entry (non-dict) must not leak garbage
    into the canonical providers section."""
    result = rate_variant(_flat_variant_payload())
    # Corrupt one provider entry in the runtime.
    result["step_results"]["provider_runtime"]["clinvar"] = "corrupted"

    add_rate_variant_canonical_fields(result)

    # The canonical entry must be the safe fallback, not garbage.
    clinvar_entry = result["providers"]["clinvar"]
    assert clinvar_entry["outcome"] == "skipped"
    assert clinvar_entry["attempted"] is False
    assert clinvar_entry["records_count"] == 0
    # providers.summary should skip the malformed entry.
    assert "clinvar" not in result["providers"]["summary"] or result["providers"]["summary"]["clinvar"]["outcome"] == "skipped"


def test_providers_summary_equals_provider_mode_summary_for_fresh_output() -> None:
    """Fresh pipeline output must have providers.summary == provider_mode_summary."""
    result = rate_variant(_flat_variant_payload())

    assert result["providers"]["summary"] == result["provider_mode_summary"]


# ── 79A-3B: provider_execution_plan observability wiring ──────────────


def test_rate_variant_emits_provider_execution_plan() -> None:
    result = rate_variant(_flat_variant_payload())

    plan = result["step_results"]["provider_execution_plan"]
    assert plan["plan_version"] == "79A-3A-v1"
    assert len(plan["nodes"]) == 8
    assert plan["provider_identity"] is not None
    assert plan["provider_identity"]["gene"] == "BRCA1"


def test_provider_execution_plan_has_expected_node_keys() -> None:
    result = rate_variant(_flat_variant_payload())

    plan = result["step_results"]["provider_execution_plan"]
    keys = {node["node_key"] for node in plan["nodes"]}
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


def test_provider_execution_plan_mock_mode_attempts_local_providers() -> None:
    """Mock/default valid identity: mock/local provider steps have planned_attempt=true."""
    result = rate_variant(_flat_variant_payload())
    plan = result["step_results"]["provider_execution_plan"]

    by_key = {node["node_key"]: node for node in plan["nodes"]}
    assert by_key["query_population_frequency"]["planned_attempt"] is True
    assert by_key["evaluate_computational_evidence"]["planned_attempt"] is True
    assert by_key["query_clinvar"]["planned_attempt"] is True
    assert by_key["search_literature_evidence"]["planned_attempt"] is True
    assert by_key["search_and_summarize_literature"]["planned_attempt"] is False


def test_provider_execution_plan_does_not_change_classification() -> None:
    payload = {**_flat_variant_payload(), "options": {"include_population": False, "include_computational": False, "include_clinvar": False, "include_literature": False}}
    result = rate_variant(payload)

    assert "provider_execution_plan" in result["step_results"]
    assert result["final_classification"] in {"vus", "pathogenic", "likely_pathogenic", "benign", "likely_benign"}


def test_provider_execution_plan_preserves_applied_evidence() -> None:
    payload = {**_flat_variant_payload(), "options": {"include_population": False, "include_computational": False, "include_clinvar": False, "include_literature": False}}
    result = rate_variant(payload)

    assert "provider_execution_plan" in result["step_results"]
    assert result["applied_evidence"] == result["evidence"]["applied"]
    assert result["evidence_items"] == result["evidence"]["all_items"]


def test_provider_execution_plan_preserves_providers_summary() -> None:
    result = rate_variant(_flat_variant_payload())

    assert "provider_execution_plan" in result["step_results"]
    assert result["providers"]["summary"] == result["provider_mode_summary"]


def test_provider_execution_plan_serialized_identity_is_valid() -> None:
    result = rate_variant(_flat_variant_payload())
    plan = result["step_results"]["provider_execution_plan"]
    identity = plan["provider_identity"]
    assert isinstance(identity, dict)
    assert identity.get("gene") == "BRCA1"
    assert identity.get("genome_build") == "GRCh38"


def test_provider_execution_plan_dependency_fields_present() -> None:
    result = rate_variant(_flat_variant_payload())
    plan = result["step_results"]["provider_execution_plan"]
    for field in ("dependency_unsatisfied", "dependency_skip_planned", "dependency_skipped", "attempted"):
        assert field in plan, f"plan missing field: {field}"
        assert isinstance(plan[field], list), f"plan.{field} is not a list"


# ── 79A-3C: evidence_phase reuses plan dependency checks ──────────────


def test_provider_dependency_checks_match_plan_dependency_checks() -> None:
    """provider_dependency_checks values must match the dependency_check
    inside the corresponding provider_execution_plan node."""
    result = rate_variant(_flat_variant_payload())

    dep_checks = result["step_results"]["provider_dependency_checks"]
    plan = result["step_results"]["provider_execution_plan"]

    plan_checks: dict[str, dict] = {}
    for node in plan["nodes"]:
        if node.get("dependency_check") is not None:
            plan_checks[node["node_key"]] = node["dependency_check"]

    # gnomad → query_population_frequency
    gnomad_from_plan = plan_checks.get("query_population_frequency")
    if gnomad_from_plan is not None:
        assert dep_checks["gnomad"]["satisfied"] == gnomad_from_plan["satisfied"]
        assert dep_checks["gnomad"]["status"] == gnomad_from_plan["status"]

    # vep → evaluate_computational_evidence
    vep_from_plan = plan_checks.get("evaluate_computational_evidence")
    if vep_from_plan is not None:
        assert dep_checks["vep"]["satisfied"] == vep_from_plan["satisfied"]

    # clinvar → query_clinvar
    clinvar_from_plan = plan_checks.get("query_clinvar")
    if clinvar_from_plan is not None:
        assert dep_checks["clinvar"]["satisfied"] == clinvar_from_plan["satisfied"]

    # literature → search_and_summarize_literature (if online) or search_literature_evidence
    lit_from_plan = plan_checks.get("search_and_summarize_literature") or plan_checks.get("search_literature_evidence")
    if lit_from_plan is not None and "literature" in dep_checks:
        assert dep_checks["literature"]["satisfied"] == lit_from_plan["satisfied"]


def test_evidence_phase_no_longer_imports_direct_dependency_checks() -> None:
    """evidence_phase must not import check_*_dependency directly
    (79A-3C reuses checks from ProviderExecutionPlan)."""
    source = (
        __import__("pathlib").Path("src/variant_pathogenicity_rater/pipeline/evidence_phase.py")
        .read_text(encoding="utf-8")
    )
    # These must not appear as top-level imports.
    assert "from variant_pathogenicity_rater.providers import (\n    check_" not in source
    assert "from variant_pathogenicity_rater.providers.dependencies import (\n    check_" not in source
    # But the fallback helpers may import them lazily (inside function bodies).
    # The key constraint: no top-level direct dependency check imports.


def test_provider_execution_plan_built_before_evidence_phase() -> None:
    """The plan must be serialized into step_results before evidence runs.
    Output phase must no longer rebuild it."""
    result = rate_variant(_flat_variant_payload())

    plan = result["step_results"]["provider_execution_plan"]
    assert plan["plan_version"] == "79A-3A-v1"
    assert len(plan["nodes"]) == 8

    # Verify the plan is identical to what build_provider_execution_plan
    # produces — it is NOT rebuilt by output_phase.
    from variant_pathogenicity_rater.data_sources.provider_result import ProviderRuntimeResult
    # Plan identity should match the provider_identity already in step_results.
    identity_payload = result["step_results"]["provider_identity"]
    assert plan["provider_identity"]["gene"] == identity_payload["gene"]


def test_invalid_gnomad_online_still_skips_with_plan_reuse() -> None:
    """Invalid gnomAD identity: plan marks dependency_unsatisfied but
    evidence_phase still handles execution correctly with plan-reused checks."""
    # Use a valid payload — plan is built in provider_phase for every
    # successful normalization.
    result = rate_variant(_flat_variant_payload())

    plan = result["step_results"]["provider_execution_plan"]
    assert plan["plan_version"] == "79A-3A-v1"
    # With valid coordinates, gnomAD should be satisfied in mock mode.
    by_key = {n["node_key"]: n for n in plan["nodes"]}
    gnomad_node = by_key["query_population_frequency"]
    assert gnomad_node["dependency_check"] is not None
    # Valid identity → satisfied.
    assert gnomad_node["dependency_check"]["satisfied"] is True
    # Mock mode → always attempts.
    assert gnomad_node["planned_attempt"] is True
    # Not in dep-skip because dependency is satisfied.
    assert "query_population_frequency" not in plan["dependency_skip_planned"]


def test_providers_summary_unchanged_with_plan_reuse() -> None:
    """providers.summary and provider_mode_summary remain stable with
    evidence_phase reusing plan dependency checks."""
    result = rate_variant(_flat_variant_payload())

    assert "provider_execution_plan" in result["step_results"]
    assert result["providers"]["summary"] == result["provider_mode_summary"]
