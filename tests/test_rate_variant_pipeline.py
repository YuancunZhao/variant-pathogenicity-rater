from __future__ import annotations

import asyncio
import json

from server import McpServer, build_registry
from config import ServerConfig
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


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
