from __future__ import annotations

import asyncio
import json

from server import McpServer, build_registry
from config import ServerConfig
from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.literature_agent import assess_literature_evidence
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.reporting import generate_report, render_literature_evidence_section
from variant_pathogenicity_rater.schemas import (
    EvidenceCode,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
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


def _rate_variant_payload() -> dict:
    return {
        "gene": "GENE1",
        "transcript": "NM_000001.1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "chromosome": "1",
        "position": 123,
        "ref": "A",
        "alt": "G",
        "disease": "GENE1-related disorder",
    }


def _literature_request() -> dict:
    return {
        "gene": "GENE1",
        "variant": "NM_000001.1:c.76A>G",
        "transcript": "NM_000001.1",
        "disease": "GENE1-related disorder",
        "literature_records": [
            {
                "evidence_type": "functional",
                "assay_validity": "validated",
                "controls_adequate": True,
                "functional_direction": "reduced_function",
                "citation": "PMID:123456",
                "claim": "Validated assay reports reduced function.",
            }
        ],
    }


def test_default_rate_variant_does_not_call_literature_agent(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("default rate_variant must not call literature agent add-on")

    monkeypatch.setattr(
        "variant_pathogenicity_rater.literature_agent.assessment.assess_literature_evidence",
        fail_if_called,
    )

    result = rate_variant(_rate_variant_payload())

    assert result["status"] == "ok"
    assert result["tool"] == "rate_variant"
    assert "assess_literature_evidence" not in result["step_results"]
    assert "literature_evidence_assessments" not in result
    assert "suggested_evidence" not in result


def test_assess_literature_evidence_output_does_not_alter_classification(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
) -> None:
    baseline = classify_acmg([], snv_variant, lof_context)
    literature_result = assess_literature_evidence(_literature_request())
    after_assessment = classify_acmg([], snv_variant, lof_context)

    assert literature_result.suggested_evidence
    assert all(item["applied"] is False for item in literature_result.suggested_evidence)
    assert all(
        item.requires_manual_review is True
        for item in literature_result.literature_evidence_assessments
    )
    assert after_assessment.final_classification == baseline.final_classification
    assert after_assessment.result_id == baseline.result_id


def test_suggested_evidence_marked_not_applied_is_review_note_only(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
) -> None:
    suggested_review_note = EvidenceItem(
        evidence_id="ev-literature-agent-suggested-ps3",
        code=EvidenceCode.PS3,
        strength=EvidenceStrength.SUPPORTING,
        direction=EvidenceDirection.PATHOGENIC,
        reason="Suggested by literature agent; not manually applied.",
        source=EvidenceSource(name="acmg_literature_evidence_agent", version="test"),
        confidence=0.8,
        requires_review=True,
        candidate_only=True,
        applied=False,
        supporting_data={
            "candidate_only": True,
            "applied": False,
            "evidence_status": "candidate",
            "requires_manual_review": True,
        },
    )

    baseline = classify_acmg([], snv_variant, lof_context)
    with_suggestion = classify_acmg([suggested_review_note], snv_variant, lof_context)

    assert suggested_review_note.applied is False
    assert with_suggestion.final_classification == baseline.final_classification
    assert with_suggestion.pathogenic_evidence_summary == []
    assert with_suggestion.evidence_items == [suggested_review_note]


def test_mcp_assess_literature_evidence_tool_schema_smoke() -> None:
    listed = _server().list_tools()["tools"]
    tool = next(item for item in listed if item["name"] == "assess_literature_evidence")
    schema = tool["inputSchema"]

    assert "rate_variant" in {item["name"] for item in listed}
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["gene", "variant"]
    assert schema["properties"]["literature_records"]["items"]["additionalProperties"] is True

    response = asyncio.run(
        _server().handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 41,
                    "method": "tools/call",
                    "params": {
                        "name": "assess_literature_evidence",
                        "arguments": {**_literature_request(), "unexpected": True},
                    },
                }
            )
        )
    )

    assert response["error"]["data"]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert any(
        "unexpected" in error for error in response["error"]["data"]["details"]["errors"]
    )


def test_report_literature_section_remains_explicit_and_separated(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
) -> None:
    classification = classify_acmg([], snv_variant, lof_context)
    default_report = generate_report(classification)
    literature_result = assess_literature_evidence(_literature_request())
    literature_section = render_literature_evidence_section(literature_result)

    assert "Literature Evidence Assessment" not in default_report.content
    assert "## Applied ACMG Evidence" in default_report.content
    assert "## Literature Evidence Assessment" in literature_section
    assert "## Applied ACMG Evidence" not in literature_section
    assert "Not automatically applied to ACMG classification" in literature_section
