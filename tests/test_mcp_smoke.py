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
        "query_clingen_erepo",
        "query_population_frequency",
        "evaluate_population_rules",
        "evaluate_computational_evidence",
        "evaluate_pvs1",
        "search_literature_evidence",
        "generate_report",
        "rate_variant_batch",
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


def test_mcp_tool_input_schemas_are_hardened_for_ci_smoke_tools() -> None:
    schemas = {
        tool["name"]: tool["inputSchema"]
        for tool in _server().list_tools()["tools"]
        if tool["name"]
        in {
            "health_check",
            "rate_variant",
            "rate_variant_batch",
            "normalize_variant",
            "query_clinvar",
            "query_clingen_erepo",
            "query_population_frequency",
            "evaluate_pvs1",
            "evaluate_computational_evidence",
            "search_literature_evidence",
            "generate_report",
        }
    }

    assert schemas
    assert all(schema["additionalProperties"] is False for schema in schemas.values())
    assert schemas["generate_report"]["properties"]["format"]["enum"] == [
        "markdown",
        "plain_text",
        "json",
    ]
    assert schemas["evaluate_computational_evidence"]["properties"]["thresholds"][
        "additionalProperties"
    ] is False
    assert schemas["rate_variant_batch"]["additionalProperties"] is False
    assert schemas["rate_variant"]["properties"]["options"]["properties"]["report_language"][
        "enum"
    ] == ["en", "zh"]
    assert schemas["rate_variant"]["properties"]["options"]["properties"]["report_mode"][
        "enum"
    ] == ["concise", "detailed", "laboratory", "clinician"]
    assert "reviewed_evidence" in schemas["rate_variant"]["properties"]
    assert "reviewed_evidence" in schemas["rate_variant_batch"]["properties"]
    assert (
        schemas["rate_variant"]["properties"]["reviewed_evidence"]["items"]["properties"][
            "evidence_status"
        ]["enum"]
        == ["reviewed_applied", "reviewed_rejected", "needs_more_info"]
    )


def test_mcp_unknown_extra_field_is_rejected_with_structured_error() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 31,
        "method": "tools/call",
        "params": {
            "name": "normalize_variant",
            "arguments": {
                "gene": "GENE1",
                "transcript": "NM_000001.1",
                "hgvs_c": "NM_000001.1:c.76A>G",
                "unexpected_extra": True,
            },
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))

    assert response["error"]["data"]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert response["error"]["data"]["recoverable"] is True
    assert any("unexpected_extra" in item for item in response["error"]["data"]["details"]["errors"])


def test_mcp_invalid_input_returns_structured_error_not_crash() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 32,
        "method": "tools/call",
        "params": {
            "name": "query_population_frequency",
            "arguments": {},
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))

    assert response["id"] == 32
    assert response["error"]["data"]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert "variant" in json.dumps(response["error"]["data"]["details"]["errors"])


def test_mcp_designated_flexible_mock_options_are_accepted() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 33,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": {
                "gene": "GENE1",
                "transcript": "NM_000001.1",
                "hgvs_c": "NM_000001.1:c.76A>G",
                "disease": "GENE1-related disorder",
                "options": {
                    "include_population": False,
                    "include_computational": False,
                    "include_clinvar": False,
                    "include_literature": False,
                    "clinvar_records": [
                        {
                            "vendor_specific_shape": {
                                "nested": ["allowed", "inside", "mock", "record"]
                            }
                        }
                    ],
                },
            },
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["status"] == "ok"
    assert tool_payload["tool"] == "rate_variant"


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
