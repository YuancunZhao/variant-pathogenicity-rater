from __future__ import annotations

import asyncio
import json

from config import ServerConfig
from server import McpServer, build_registry
from variant_pathogenicity_rater.cli import main
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
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


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68A>G",
        "hgvs_p": "NP_009225.1:p.Glu23Val",
        "chromosome": "17",
        "position": 43092919,
        "ref": "A",
        "alt": "G",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }
    payload.update(overrides)
    return payload


def _reviewed(
    code: str = "PS3",
    strength: str = "strong",
    direction: str = "pathogenic",
    status: str = "reviewed_applied",
    **overrides: object,
) -> dict[str, object]:
    record: dict[str, object] = {
        "source_candidate_evidence_id": "ev-candidate-ps3",
        "acmg_code": code,
        "strength": strength,
        "direction": direction,
        "curator_decision": f"Apply {code} after manual review.",
        "curator_name": "Test Curator",
        "review_date": "2026-05-26",
        "rationale": f"Curator-reviewed rationale for {code}.",
        "citation": "PMID:123456",
        "provenance": {"review_system": "pytest", "source": "manual"},
        "override_reason": "Manual review confirmed applicability.",
        "evidence_status": status,
        "audit_trail": [
            {
                "event_id": "audit-reviewed-input",
                "event_type": "curator_review_completed",
                "actor": "Test Curator",
                "notes": ["reviewed in pytest"],
            }
        ],
    }
    record.update(overrides)
    return record


def _candidate_ps3() -> dict[str, object]:
    return {
        "evidence_id": "ev-candidate-ps3",
        "code": "PS3",
        "strength": "strong",
        "direction": "pathogenic",
        "reason": "Candidate functional note should remain traceable.",
        "source": {"name": "literature_candidate", "version": "test"},
        "confidence": 0.5,
        "requires_review": True,
        "candidate_only": True,
        "applied": False,
        "supporting_data": {
            "candidate_only": True,
            "applied": False,
            "evidence_status": "candidate",
        },
    }


def test_reviewed_ps3_promotes_linked_candidate_without_mutating_candidate() -> None:
    result = rate_variant(
        _payload(
            reviewed_evidence=[_reviewed()],
            options={
                **_payload()["options"],
                "mock_supplemental_evidence_items": [_candidate_ps3()],
            },
        )
    )

    applied_ps3 = [item for item in result["applied_evidence"] if item["code"] == "PS3"]
    candidate_ps3 = [item for item in result["review_note_evidence"] if item["evidence_id"] == "ev-candidate-ps3"]

    assert len(applied_ps3) == 1
    assert applied_ps3[0]["source"]["name"] == "manual_reviewed_evidence"
    assert applied_ps3[0]["supporting_data"]["source_candidate_evidence_id"] == "ev-candidate-ps3"
    assert applied_ps3[0]["supporting_data"]["curator_decision"] == "Apply PS3 after manual review."
    assert candidate_ps3 and candidate_ps3[0]["applied"] is False
    assert result["reviewed_evidence"][0]["evidence_status"] == "reviewed_applied"
    assert result["classification_result"]["human_review_required"] is True


def test_reviewed_pp1_applies_as_supporting_pathogenic_evidence() -> None:
    result = rate_variant(
        _payload(reviewed_evidence=[_reviewed("PP1", "supporting", source_candidate_evidence_id=None)])
    )

    pp1 = [item for item in result["applied_evidence"] if item["code"] == "PP1"]

    assert len(pp1) == 1
    assert pp1[0]["strength"] == "supporting"
    assert pp1[0]["triggered_by"] == ["manual_reviewed_evidence"]


def test_reviewed_rejection_is_visible_but_not_applied() -> None:
    result = rate_variant(
        _payload(
            reviewed_evidence=[
                _reviewed(
                    status="reviewed_rejected",
                    rationale="Assay was not valid for disease mechanism.",
                )
            ],
            options={
                **_payload()["options"],
                "mock_supplemental_evidence_items": [_candidate_ps3()],
            },
        )
    )

    assert result["applied_evidence"] == []
    candidate = next(item for item in result["review_note_evidence"] if item["evidence_id"] == "ev-candidate-ps3")
    note = next(item for item in result["review_note_evidence"] if item["source"]["name"] == "manual_reviewed_evidence")
    assert candidate["applied"] is False
    assert note["strength"] == "none"
    assert note["applied"] is False
    assert note["supporting_data"]["evidence_status"] == "reviewed_rejected"
    assert note["supporting_data"]["source_candidate_evidence_id"] == "ev-candidate-ps3"
    assert "Manual Reviewed Evidence" in result["report_text"]
    assert "Assay was not valid" in result["report_text"]


def test_needs_more_info_is_review_note_only() -> None:
    result = rate_variant(
        _payload(
            reviewed_evidence=[_reviewed(status="needs_more_info")],
            options={
                **_payload()["options"],
                "mock_supplemental_evidence_items": [_candidate_ps3()],
            },
        )
    )

    assert result["applied_evidence"] == []
    note = next(item for item in result["review_note_evidence"] if item["source"]["name"] == "manual_reviewed_evidence")
    assert note["strength"] == "none"
    assert note["applied"] is False
    assert note["supporting_data"]["evidence_status"] == "needs_more_info"


def test_invalid_reviewed_evidence_is_rejected_with_review_flag() -> None:
    result = rate_variant(_payload(reviewed_evidence=[_reviewed(strength="none")]))

    assert result["applied_evidence"] == []
    assert any("reviewed_evidence[0] validation failed" in item for item in result["limitations"])
    assert any(flag["code"] == "INVALID_REVIEWED_EVIDENCE" for flag in result["review_flags"])
    assert result["reviewed_evidence"] == []


def test_reviewed_evidence_source_id_mismatch_does_not_apply() -> None:
    result = rate_variant(
        _payload(reviewed_evidence=[_reviewed(source_candidate_evidence_id="ev-candidate-other-record")])
    )

    assert result["applied_evidence"] == []
    assert any("ev-candidate-other-record" in item for item in result["limitations"])
    assert any(flag["code"] == "REVIEWED_SOURCE_CANDIDATE_NOT_FOUND" for flag in result["review_flags"])
    note = next(item for item in result["review_note_evidence"] if item["source"]["name"] == "manual_reviewed_evidence")
    assert note["applied"] is False
    assert note["supporting_data"]["source_candidate_evidence_id"] == "ev-candidate-other-record"


def test_conflicting_reviewed_evidence_triggers_review_flag_and_combiner_conflict() -> None:
    existing = {
        "evidence_id": "ev-applied-ps3",
        "code": "PS3",
        "strength": "strong",
        "direction": "pathogenic",
        "reason": "Existing applied PS3.",
        "source": {"name": "manual_fixture", "version": "test"},
        "confidence": 0.8,
        "requires_review": True,
        "candidate_only": False,
        "applied": True,
    }
    result = rate_variant(
        _payload(
            reviewed_evidence=[_reviewed(direction="benign", source_candidate_evidence_id=None)],
            options={
                **_payload()["options"],
                "mock_supplemental_evidence_items": [existing],
            },
        )
    )

    assert any(flag["code"] == "REVIEWED_EVIDENCE_DIRECTION_CONFLICT" for flag in result["review_flags"])
    assert result["final_classification"] == "vus"
    assert result["classification_result"]["conflicting_evidence"]


def test_classification_change_comes_from_existing_combiner() -> None:
    no_review = rate_variant(_payload())
    reviewed = rate_variant(
        _payload(
            reviewed_evidence=[
                _reviewed("PS3", "strong", source_candidate_evidence_id=None),
                _reviewed("PM1", "moderate", source_candidate_evidence_id=None),
            ]
        )
    )

    assert no_review["final_classification"] == "vus"
    assert reviewed["final_classification"] == "likely_pathogenic"
    assert reviewed["classification_result"]["applied_combination_rule"] == "likely_pathogenic: 1 strong + 1-2 moderate"
    assert "classify_acmg" in reviewed["step_results"]


def test_literature_suggested_ps3_changes_classification_only_after_reviewed_applied() -> None:
    literature_payload = _payload(
        gene="GENE1",
        transcript="NM_000001.1",
        hgvs_c="NM_000001.1:c.76A>G",
        hgvs_p="NP_000001.1:p.Lys26Arg",
        chromosome="1",
        position=123,
        ref="A",
        alt="G",
        disease="GENE1-related example disorder",
        options={
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": True,
        },
    )
    no_review = rate_variant(literature_payload)
    ps3_candidate = next(
        item
        for item in no_review["review_note_evidence"]
        if item["code"] == "PS3" and item["source"]["name"] == "mock_literature"
    )

    reviewed = rate_variant(
        {
            **literature_payload,
            "reviewed_evidence": [
                _reviewed("PS3", "strong", source_candidate_evidence_id=ps3_candidate["evidence_id"]),
                _reviewed("PM1", "moderate", source_candidate_evidence_id=None),
            ],
        }
    )

    assert no_review["final_classification"] == "vus"
    assert no_review["applied_evidence"] == []
    assert reviewed["final_classification"] == "likely_pathogenic"
    assert reviewed["classification_result"]["applied_combination_rule"] == "likely_pathogenic: 1 strong + 1-2 moderate"
    assert any(item["evidence_id"] == ps3_candidate["evidence_id"] for item in reviewed["review_note_evidence"])
    applied_ps3 = next(item for item in reviewed["applied_evidence"] if item["code"] == "PS3")
    assert applied_ps3["source"]["name"] == "manual_reviewed_evidence"
    assert applied_ps3["supporting_data"]["source_candidate_evidence_id"] == ps3_candidate["evidence_id"]


def test_batch_reviewed_evidence_is_per_record_only() -> None:
    records = [_payload(position=43092919), _payload(position=43092920)]
    result = rate_variant_batch(
        {
            "records": records,
            "reviewed_evidence": {
                "records": [{"input_index": 1, "reviewed_evidence": [_reviewed(source_candidate_evidence_id=None)]}]
            },
        }
    )

    first, second = result["results"]

    assert first["applied_evidence"] == []
    assert [item["code"] for item in second["applied_evidence"]] == ["PS3"]


def test_report_manual_reviewed_evidence_section_preserves_review_metadata() -> None:
    result = rate_variant(
        _payload(reviewed_evidence=[_reviewed(source_candidate_evidence_id=None)])
    )

    report = result["report_text"]

    assert "## Manual Reviewed Evidence" in report
    assert "Curator decision: Apply PS3 after manual review." in report
    assert "Curator: Test Curator" in report
    assert "Review date: 2026-05-26" in report
    assert "Override reason: Manual review confirmed applicability." in report


def test_mcp_rate_variant_and_batch_accept_reviewed_evidence() -> None:
    server = _server()
    single = {
        "jsonrpc": "2.0",
        "id": 52,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": _payload(reviewed_evidence=[_reviewed(source_candidate_evidence_id=None)]),
        },
    }
    batch = {
        "jsonrpc": "2.0",
        "id": 53,
        "method": "tools/call",
        "params": {
            "name": "rate_variant_batch",
            "arguments": {
                "records": [_payload()],
                "reviewed_evidence": {
                    "records": [{"input_index": 0, "reviewed_evidence": [_reviewed(source_candidate_evidence_id=None)]}]
                },
            },
        },
    }

    single_response = asyncio.run(server.handle_message(json.dumps(single)))
    batch_response = asyncio.run(server.handle_message(json.dumps(batch)))
    single_payload = json.loads(single_response["result"]["content"][0]["text"])
    batch_payload = json.loads(batch_response["result"]["content"][0]["text"])

    assert single_payload["applied_evidence"][0]["code"] == "PS3"
    assert batch_payload["results"][0]["applied_evidence"][0]["code"] == "PS3"


def test_mcp_reviewed_evidence_schema_rejects_extra_fields() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 54,
        "method": "tools/call",
        "params": {
            "name": "rate_variant",
            "arguments": _payload(
                reviewed_evidence=[
                    _reviewed(source_candidate_evidence_id=None, unexpected_review_field=True)
                ]
            ),
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))

    assert response["error"]["data"]["code"] == "SCHEMA_VALIDATION_ERROR"
    assert any(
        "unexpected_review_field" in item
        for item in response["error"]["data"]["details"]["errors"]
    )


def test_cli_reviewed_evidence_single_and_batch(capsys, tmp_path) -> None:
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(json.dumps({"reviewed_evidence": [_reviewed(source_candidate_evidence_id=None)]}), encoding="utf-8")
    batch_path = tmp_path / "batch.jsonl"
    batch_path.write_text(json.dumps(_payload()), encoding="utf-8")
    batch_reviewed_path = tmp_path / "batch_reviewed.json"
    batch_reviewed_path.write_text(
        json.dumps({"records": [{"input_index": 0, "reviewed_evidence": [_reviewed(source_candidate_evidence_id=None)]}]}),
        encoding="utf-8",
    )

    single_exit = main(
        [
            "rate",
            "--gene",
            "BRCA1",
            "--transcript",
            "NM_007294.4",
            "--hgvs-c",
            "NM_007294.4:c.68A>G",
            "--hgvs-p",
            "NP_009225.1:p.Glu23Val",
            "--chromosome",
            "17",
            "--position",
            "43092919",
            "--ref",
            "A",
            "--alt",
            "G",
            "--disease",
            "Hereditary breast and ovarian cancer",
            "--reviewed-evidence",
            str(reviewed_path),
        ]
    )
    single_payload = json.loads(capsys.readouterr().out)

    batch_exit = main(
        [
            "batch",
            "--input",
            str(batch_path),
            "--format",
            "jsonl",
            "--reviewed-evidence",
            str(batch_reviewed_path),
        ]
    )
    batch_payload = json.loads(capsys.readouterr().out)

    assert single_exit == 0
    assert batch_exit == 0
    assert single_payload["applied_evidence"][0]["source"]["name"] == "manual_reviewed_evidence"
    assert batch_payload["results"][0]["applied_evidence"][0]["source"]["name"] == "manual_reviewed_evidence"


def test_cli_reviewed_evidence_file_json_error_is_preserved(capsys, tmp_path) -> None:
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text("{not-json", encoding="utf-8")

    exit_code = main(
        [
            "rate",
            "--gene",
            "BRCA1",
            "--transcript",
            "NM_007294.4",
            "--hgvs-c",
            "NM_007294.4:c.68A>G",
            "--chromosome",
            "17",
            "--position",
            "43092919",
            "--ref",
            "A",
            "--alt",
            "G",
            "--reviewed-evidence",
            str(reviewed_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "reviewed evidence file is not valid JSON" in captured.err
