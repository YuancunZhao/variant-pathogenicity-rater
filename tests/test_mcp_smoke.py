from __future__ import annotations

import asyncio
import json

from server import McpServer, build_registry
from config import ServerConfig
from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.schemas import (
    ComputationalPrediction,
    EvidenceCode,
    EvidenceDirection,
    EvidenceStrength,
    GeneDiseaseContext,
    Variant,
)


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


def test_mcp_registry_lists_ci_smoke_tools() -> None:
    tool_names = {tool.name for tool in build_registry().list_tools()}

    assert {
        "health_check",
        "normalize_variant",
        "query_clinvar",
        "query_population_frequency",
        "evaluate_population_rules",
        "evaluate_computational_evidence",
        "evaluate_pvs1",
        "search_literature_evidence",
        "generate_report",
    }.issubset(tool_names)


def test_mcp_jsonrpc_initialize_and_list_tools() -> None:
    server = _server()

    initialize = asyncio.run(
        server.handle_message('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    )
    listed = asyncio.run(
        server.handle_message('{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
    )

    assert initialize["result"]["serverInfo"]["name"] == "variant-pathogenicity-rater-test"
    assert any(tool["name"] == "normalize_variant" for tool in listed["result"]["tools"])


def test_mcp_generate_report_tool_smoke(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    classification = classify_acmg(
        [evidence_factory(EvidenceCode.BA1, EvidenceStrength.STAND_ALONE, EvidenceDirection.BENIGN)],
        snv_variant,
        lof_context,
    )
    server = _server()
    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "generate_report",
            "arguments": {
                "classification_result": json.loads(classification.model_dump_json()),
                "format": "json",
                "mode": "concise",
            },
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["status"] == "ok"
    assert tool_payload["report"]["summary"]["final_classification"] == "benign"
    assert tool_payload["report"]["human_review_required"] is True


def test_mcp_evaluate_computational_evidence_tool_smoke(snv_variant: Variant) -> None:
    source = {"name": "mock_test_predictions", "version": "fixture-v1"}
    predictions = [
        ComputationalPrediction(
            source=source,
            method="REVEL",
            score=0.9,
            prediction="deleterious",
        ),
        ComputationalPrediction(
            source=source,
            method="CADD",
            score=28.0,
            prediction="deleterious",
        ),
    ]
    server = _server()
    request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "evaluate_computational_evidence",
            "arguments": {
                "variant": json.loads(snv_variant.model_dump_json()),
                "computational_predictions": [
                    json.loads(prediction.model_dump_json()) for prediction in predictions
                ],
            },
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["status"] == "ok"
    assert tool_payload["evidence_items"][0]["code"] == "PP3"
    assert tool_payload["criterion_assessments"][0]["strength"] == "supporting"
