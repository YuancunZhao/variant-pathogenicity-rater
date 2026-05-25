from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.literature_agent import (
    assess_case_count_evidence,
    assess_de_novo_evidence,
    assess_functional_evidence,
    assess_literature_evidence,
    assess_phenotype_specificity,
    assess_same_amino_acid_or_residue,
    assess_segregation_evidence,
    assess_trans_observation,
)
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.reporting import render_literature_evidence_section
from variant_pathogenicity_rater.schemas import GeneDiseaseContext, Variant


ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))

from server import McpServer, build_registry  # noqa: E402
from config import ServerConfig  # noqa: E402


def _request(records: list[dict]) -> dict:
    return {
        "gene": "GENE1",
        "variant": "NM_000001.1:c.76A>G",
        "transcript": "NM_000001.1",
        "disease": "GENE1 disorder",
        "inheritance": "autosomal dominant",
        "phenotype": ["HP:0001250"],
        "literature_records": records,
    }


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


def test_functional_assay_valid_suggests_ps3() -> None:
    item = assess_functional_evidence(
        {
            "evidence_type": "functional",
            "assay_validity": "validated",
            "controls_adequate": True,
            "functional_direction": "reduced_function",
        }
    )

    assert item.candidate_code == "PS3"
    assert item.suggested_strength == "supporting"
    assert item.requires_manual_review is True


def test_weak_assay_is_ps3_candidate_only() -> None:
    item = assess_functional_evidence(
        {"evidence_type": "functional", "functional_direction": "reduced_function"}
    )

    assert item.candidate_code == "PS3_candidate"
    assert item.suggested_strength == "none"


def test_benign_functional_assay_suggests_bs3() -> None:
    item = assess_functional_evidence(
        {
            "evidence_type": "functional",
            "assay_validity": "validated",
            "controls_adequate": True,
            "functional_direction": "normal",
        }
    )

    assert item.candidate_code == "BS3"
    assert item.suggested_strength == "supporting"


def test_confirmed_de_novo_suggests_ps2() -> None:
    item = assess_de_novo_evidence(
        {"evidence_type": "de_novo", "confirmed_de_novo": True, "parentage_confirmed": True}
    )

    assert item.candidate_code == "PS2"


def test_unconfirmed_de_novo_suggests_pm6() -> None:
    item = assess_de_novo_evidence({"evidence_type": "de_novo", "de_novo_reported": True})

    assert item.candidate_code == "PM6"
    assert item.suggested_strength == "supporting"


def test_segregation_family_suggests_pp1() -> None:
    item = assess_segregation_evidence(
        {"evidence_type": "segregation", "segregation_count": 3, "pedigree_context": True}
    )

    assert item.candidate_code == "PP1"


def test_isolated_case_report_is_ps4_candidate_only() -> None:
    item = assess_case_count_evidence({"evidence_type": "case_report", "case_count": 1})

    assert item.candidate_code == "PS4_candidate"
    assert item.suggested_strength == "none"


def test_phenotype_match_is_pp4_candidate_only() -> None:
    item = assess_phenotype_specificity(
        {"evidence_type": "phenotype_specificity", "phenotype_match_level": "specific"}
    )

    assert item.candidate_code == "PP4_candidate"
    assert item.suggested_strength == "none"


def test_trans_confirmed_suggests_pm3() -> None:
    item = assess_trans_observation({"evidence_type": "trans_observation", "phase": "trans"})

    assert item.candidate_code == "PM3"


def test_same_amino_acid_suggests_ps1() -> None:
    item = assess_same_amino_acid_or_residue(
        {"evidence_type": "same_amino_acid", "residue_relationship": "same_amino_acid"}
    )

    assert item.candidate_code == "PS1"


def test_same_residue_different_missense_suggests_pm5() -> None:
    item = assess_same_amino_acid_or_residue(
        {
            "evidence_type": "same_residue",
            "residue_relationship": "same_residue_different_missense",
        }
    )

    assert item.candidate_code == "PM5"


def test_all_suggested_evidence_does_not_change_final_classification(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
) -> None:
    before = classify_acmg([], snv_variant, lof_context)
    result = assess_literature_evidence(
        _request(
            [
                {
                    "evidence_type": "functional",
                    "assay_validity": "validated",
                    "controls_adequate": True,
                    "functional_direction": "reduced_function",
                    "citation": "PMID:1",
                }
            ]
        )
    )
    after = classify_acmg([], snv_variant, lof_context)

    assert result.suggested_evidence[0]["applied"] is False
    assert before.final_classification == after.final_classification


def test_mcp_tool_returns_stable_schema() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 40,
        "method": "tools/call",
        "params": {
            "name": "assess_literature_evidence",
            "arguments": _request(
                [
                    {
                        "evidence_type": "de_novo",
                        "de_novo_reported": True,
                        "pmid": "12345",
                    }
                ]
            ),
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["status"] == "ok"
    assert payload["tool"] == "assess_literature_evidence"
    assert payload["suggested_evidence"][0]["code"] == "PM6"
    assert payload["applied_evidence"] == []
    assert payload["final_classification_changed"] is False


def test_report_section_is_clearly_separated() -> None:
    result = assess_literature_evidence(
        _request(
            [
                {
                    "evidence_type": "case_report",
                    "case_count": 1,
                    "citation": "PMID:999",
                    "claim": "Single case report.",
                }
            ]
        )
    )

    section = render_literature_evidence_section(result)

    assert "## Literature Evidence Assessment" in section
    assert "Not automatically applied to ACMG classification" in section
    assert "## Applied ACMG Evidence" not in section


def test_no_changes_to_existing_rate_variant_outputs() -> None:
    payload = {
        "gene": "GENE1",
        "transcript": "NM_000001.1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "chromosome": "1",
        "position": 123,
        "ref": "A",
        "alt": "G",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }

    output = rate_variant(payload)

    assert output["tool"] == "rate_variant"
    assert "literature_evidence_assessments" not in output
    assert "suggested_evidence" not in output
