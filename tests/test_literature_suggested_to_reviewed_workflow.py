from __future__ import annotations

import asyncio
import json

from config import ServerConfig
from server import McpServer, build_registry
from variant_pathogenicity_rater.cli import main
from variant_pathogenicity_rater.literature_agent import (
    assess_literature_evidence,
    create_reviewed_evidence_drafts,
)
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


def _literature_payload(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "gene": "GENE1",
        "variant": "NM_000001.1:c.76A>G",
        "transcript": "NM_000001.1",
        "disease": "GENE1-related disorder",
        "inheritance": "autosomal dominant",
        "literature_records": records,
    }


def _rate_payload(reviewed_evidence: list[dict[str, object]] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "gene": "GENE1",
        "transcript": "NM_000001.1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "chromosome": "1",
        "position": 123,
        "ref": "A",
        "alt": "G",
        "disease": "GENE1-related disorder",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }
    if reviewed_evidence is not None:
        payload["reviewed_evidence"] = reviewed_evidence
    return payload


def test_ps3_suggested_becomes_needs_more_info_reviewed_draft() -> None:
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "record_id": "lit-ps3-1",
                    "evidence_type": "functional",
                    "assay_validity": "validated",
                    "controls_adequate": True,
                    "functional_direction": "reduced_function",
                    "claim": "Validated assay reports reduced function.",
                    "citation": "PMID:123456",
                    "pmid": "123456",
                }
            ]
        )
    )

    result = create_reviewed_evidence_drafts(assessment)
    draft = result["reviewed_evidence"][0]

    assert result["status"] == "ok"
    assert draft["acmg_code"] == "PS3"
    assert draft["suggested_strength"] == "supporting"
    assert draft["evidence_status"] == "needs_more_info"
    assert draft["curator_decision"] == "pending"
    assert draft["requires_manual_review"] is True
    assert "Validated assay reports reduced function" in draft["rationale"]


def test_pp1_draft_preserves_source_candidate_evidence_id() -> None:
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "record_id": "lit-pp1-family-a",
                    "evidence_type": "segregation",
                    "segregation_count": 4,
                    "pedigree_context": True,
                    "claim": "Variant segregates in four affected relatives.",
                }
            ]
        )
    )

    draft = create_reviewed_evidence_drafts(assessment)["reviewed_evidence"][0]

    assert assessment.suggested_evidence[0]["source_candidate_evidence_id"] == "lit-pp1-family-a"
    assert draft["source_candidate_evidence_id"] == "lit-pp1-family-a"
    assert draft["provenance"]["source_candidate_evidence_id"] == "lit-pp1-family-a"


def test_pmid_doi_citation_and_review_questions_are_preserved() -> None:
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "record_id": "lit-citation-1",
                    "evidence_type": "functional",
                    "assay_validity": "validated",
                    "controls_adequate": True,
                    "functional_direction": "reduced_function",
                    "claim": "Assay claim.",
                    "citation": "Smith et al. 2026",
                    "pmid": "987654",
                    "doi": "10.1234/example",
                }
            ]
        )
    )

    draft = create_reviewed_evidence_drafts(assessment)["reviewed_evidence"][0]

    assert draft["citation"] == "Smith et al. 2026"
    assert draft["pmid"] == "987654"
    assert draft["doi"] == "10.1234/example"
    assert draft["extracted_claim"] == "Assay claim."
    assert draft["review_questions"]
    assert draft["provenance"]["pmid"] == "987654"
    assert draft["provenance"]["doi"] == "10.1234/example"


def test_draft_does_not_alter_classification_or_apply_evidence() -> None:
    base = rate_variant(_rate_payload())
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "evidence_type": "functional",
                    "assay_validity": "validated",
                    "controls_adequate": True,
                    "functional_direction": "reduced_function",
                    "claim": "Validated assay reports reduced function.",
                }
            ]
        )
    )
    draft = create_reviewed_evidence_drafts(assessment)["reviewed_evidence"]
    with_draft = rate_variant(_rate_payload(reviewed_evidence=draft))

    assert base["final_classification"] == "vus"
    assert with_draft["final_classification"] == base["final_classification"]
    assert with_draft["applied_evidence"] == []


def test_curator_must_change_status_to_reviewed_applied_before_combiner_sees_it() -> None:
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "record_id": "lit-ps3-review",
                    "evidence_type": "functional",
                    "assay_validity": "validated",
                    "controls_adequate": True,
                    "functional_direction": "reduced_function",
                    "claim": "Validated assay reports reduced function.",
                    "citation": "PMID:123456",
                }
            ]
        )
    )
    draft = create_reviewed_evidence_drafts(assessment)["reviewed_evidence"][0]
    pending = rate_variant(_rate_payload(reviewed_evidence=[draft]))

    curated = {
        key: value
        for key, value in draft.items()
        if key
        in {
            "source_candidate_evidence_id",
            "acmg_code",
            "strength",
            "direction",
            "curator_decision",
            "curator_name",
            "review_date",
            "rationale",
            "citation",
            "provenance",
            "override_reason",
            "evidence_status",
            "audit_trail",
        }
    }
    curated.update(
        {
            "source_candidate_evidence_id": None,
            "curator_decision": "Apply PS3 after manual review.",
            "curator_name": "Test Curator",
            "review_date": "2026-05-26",
            "override_reason": "Manual review confirmed applicability.",
            "evidence_status": "reviewed_applied",
        }
    )
    applied = rate_variant(_rate_payload(reviewed_evidence=[curated]))

    assert pending["applied_evidence"] == []
    assert any("validation failed" in item for item in pending["limitations"])
    assert [item["code"] for item in applied["applied_evidence"]] == ["PS3"]
    assert applied["classification_result"]["pathogenic_evidence_summary"][0].startswith("PS3")


def test_cli_literature_draft_reviewed_command(tmp_path) -> None:
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "record_id": "lit-cli-1",
                    "evidence_type": "functional",
                    "assay_validity": "validated",
                    "controls_adequate": True,
                    "functional_direction": "reduced_function",
                    "claim": "CLI assay claim.",
                }
            ]
        )
    )
    assessment_path = tmp_path / "assessment.json"
    output_path = tmp_path / "reviewed_draft.json"
    assessment_path.write_text(assessment.model_dump_json(), encoding="utf-8")

    exit_code = main(
        [
            "literature-draft-reviewed",
            "--literature-assessment-json",
            str(assessment_path),
            "--output",
            str(output_path),
        ]
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["tool"] == "create_reviewed_evidence_draft"
    assert payload["reviewed_evidence"][0]["evidence_status"] == "needs_more_info"


def test_mcp_create_reviewed_evidence_draft_tool() -> None:
    assessment = assess_literature_evidence(
        _literature_payload(
            [
                {
                    "record_id": "lit-mcp-1",
                    "evidence_type": "segregation",
                    "segregation_count": 2,
                    "pedigree_context": True,
                    "claim": "MCP segregation claim.",
                }
            ]
        )
    )
    response = asyncio.run(
        _server().handle_message(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 55,
                    "method": "tools/call",
                    "params": {
                        "name": "create_reviewed_evidence_draft",
                        "arguments": {
                            "literature_assessment_json": json.loads(assessment.model_dump_json())
                        },
                    },
                }
            )
        )
    )
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["status"] == "ok"
    assert payload["reviewed_evidence"][0]["acmg_code"] == "PP1"
    assert payload["applied_evidence"] == []
    assert payload["final_classification_changed"] is False


def test_malformed_assessment_returns_structured_error() -> None:
    result = create_reviewed_evidence_drafts({"suggested_evidence": []})

    assert result["status"] == "error"
    assert result["reviewed_evidence"] == []
    assert result["errors"][0]["message"] == "literature_evidence_assessments must be a list."
    assert result["applied_evidence"] == []
