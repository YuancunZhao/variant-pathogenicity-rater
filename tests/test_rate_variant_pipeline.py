from __future__ import annotations

import asyncio
import json

from server import McpServer, build_registry
from config import ServerConfig
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
    assert "applied_evidence" in result
    assert "review_note_evidence" in result
    assert "review_flags" in result
    assert "provenance" in result
    assert result["report_text"]
    assert result["limitations"]
    assert result["human_review_required"] is True

    completed_steps = {event["tool_name"] for event in result["audit_trail"]}
    assert {
        "normalize_variant",
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
