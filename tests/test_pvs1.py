from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from config import ServerConfig  # noqa: E402
from server import McpServer, build_registry  # noqa: E402
from variant_pathogenicity_rater.acmg.pvs1 import evaluate_pvs1  # noqa: E402
from variant_pathogenicity_rater.schemas import (  # noqa: E402
    GeneDiseaseContext,
    Transcript,
    Variant,
)


def _load_example(name: str) -> tuple[Variant, Transcript, GeneDiseaseContext]:
    payload = json.loads((ROOT / "examples" / name).read_text())
    return (
        Variant.model_validate(payload["variant"]),
        Transcript.model_validate(payload["transcript"]),
        GeneDiseaseContext.model_validate(payload["gene_disease_context"]),
    )


def test_frameshift_with_known_lof_and_nmd_triggers_pvs1() -> None:
    variant, transcript, context = _load_example("pvs1_frameshift_input.json")

    result = evaluate_pvs1(variant, transcript, context)

    assert result.outcome == "PVS1"
    assert result.evidence_item is not None
    assert result.evidence_item.strength == "very_strong"
    assert result.evidence_item.supporting_data["nmd_predicted"] is True
    assert result.downgrade_rationale == []


def test_nonsense_with_known_lof_mechanism_triggers_pvs1(
    snv_variant,
    nonsense_transcript,
    lof_context,
) -> None:
    variant = snv_variant
    variant.hgvs_p = "NP_000001.1:p.Lys26Ter"
    variant.hgvs_c = "NM_000001.1:c.76A>T"
    variant.alt = "T"

    result = evaluate_pvs1(variant, nonsense_transcript, lof_context)

    assert result.outcome == "PVS1"
    assert result.evidence_item is not None
    assert result.evidence_item.code == "PVS1"
    assert result.predicted_consequence == "nonsense"


def test_nonsense_mock_example_triggers_pvs1() -> None:
    variant, transcript, context = _load_example("pvs1_nonsense_input.json")

    result = evaluate_pvs1(variant, transcript, context)

    assert result.outcome == "PVS1"
    assert result.predicted_consequence == "nonsense"
    assert result.evidence_item is not None
    assert result.evidence_item.supporting_data["applied_pvs1_level"] == "PVS1"


def test_terminal_canonical_splice_is_downgraded_to_supporting() -> None:
    variant, transcript, context = _load_example("pvs1_terminal_splice_input.json")

    result = evaluate_pvs1(variant, transcript, context)

    assert result.outcome == "PVS1_Supporting"
    assert result.evidence_item is not None
    assert result.evidence_item.strength == "supporting"
    assert any("last exon" in reason for reason in result.downgrade_rationale)
    assert any(flag.code == "POSSIBLE_IN_FRAME_RESCUE" for flag in result.review_flags)


def test_start_loss_is_candidate_only_with_review_flag() -> None:
    variant, transcript, context = _load_example("pvs1_start_loss_input.json")

    result = evaluate_pvs1(variant, transcript, context)

    assert result.outcome == "candidate_only"
    assert result.evidence_item is not None
    assert result.evidence_item.strength == "none"
    assert result.evidence_item.supporting_data["candidate_only"] is True
    assert result.review_flags[0].code == "START_LOSS_REVIEW"


def test_small_indel_lof_with_in_frame_rescue_is_downgraded_to_supporting() -> None:
    variant, transcript, context = _load_example("pvs1_inframe_rescue_input.json")

    result = evaluate_pvs1(variant, transcript, context)

    assert result.outcome == "PVS1_Supporting"
    assert result.predicted_consequence == "small_indel_lof"
    assert result.evidence_item is not None
    assert result.evidence_item.strength == "supporting"
    assert any("in-frame rescue" in reason for reason in result.downgrade_rationale)
    assert any(flag.code == "POSSIBLE_IN_FRAME_RESCUE" for flag in result.review_flags)


def test_nmd_unknown_does_not_trigger_pvs1_strong(
    snv_variant,
    nonsense_transcript,
    lof_context,
) -> None:
    lof_context.nmd_prediction_available = False
    lof_context.nmd_predicted = None

    result = evaluate_pvs1(snv_variant, nonsense_transcript, lof_context)

    assert result.outcome == "PVS1_Supporting"
    assert result.evidence_item is not None
    assert result.evidence_item.strength == "supporting"
    assert result.requires_review is True


def test_canonical_splice_without_consequence_detail_requires_review(snv_variant, lof_context) -> None:
    snv_variant.hgvs_c = "NM_000001.1:c.76+1G>T"
    snv_variant.hgvs_p = None
    transcript = Transcript(
        accession="NM_000001",
        version="1",
        gene_symbol="GENE1",
        hgvs_c="NM_000001.1:c.76+1G>T",
        consequence=None,
        canonical=True,
    )

    result = evaluate_pvs1(snv_variant, transcript, lof_context)

    assert result.outcome == "PVS1_Supporting"
    assert result.evidence_item is not None
    assert result.evidence_item.strength == "supporting"
    assert result.requires_review is True


def test_lof_mechanism_must_be_confirmed() -> None:
    variant, transcript, context = _load_example("pvs1_frameshift_input.json")
    context.lof_is_known_mechanism = False

    result = evaluate_pvs1(variant, transcript, context)

    assert result.outcome == "not_triggered"
    assert result.evidence_item is None
    assert result.review_flags[0].code == "LOF_MECHANISM_NOT_CONFIRMED"


def test_context_accepts_requested_aliases() -> None:
    context = GeneDiseaseContext.model_validate(
        {
            "gene": "BRCA2",
            "disease": "Hereditary breast and ovarian cancer syndrome",
            "inheritance": "autosomal dominant",
            "lof_is_known_mechanism": True,
            "transcript_is_biologically_relevant": True,
            "nmd_prediction_available": True,
        }
    )

    assert context.gene_symbol == "BRCA2"
    assert context.disease_name.startswith("Hereditary")
    assert context.inheritance_mode == "autosomal dominant"


def test_mcp_evaluate_pvs1_tool_is_registered() -> None:
    from server import build_registry

    registry = build_registry()
    tool_names = {tool.name for tool in registry.list_tools()}

    assert "evaluate_pvs1" in tool_names


def test_mcp_evaluate_pvs1_tool_returns_reasoning_chain() -> None:
    variant, transcript, context = _load_example("pvs1_nonsense_input.json")
    server = McpServer(
        ServerConfig(
            server_name="variant-pathogenicity-rater-test",
            server_version="0.1.0",
            log_level="ERROR",
            tools_package="tools",
            enable_health_tool=True,
            environment="test",
        ),
        build_registry(),
    )
    request = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "evaluate_pvs1",
            "arguments": {
                "variant": json.loads(variant.model_dump_json()),
                "transcript": json.loads(transcript.model_dump_json()),
                "gene_disease_context": json.loads(context.model_dump_json()),
            },
        },
    }

    response = asyncio.run(server.handle_message(json.dumps(request)))
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["status"] == "ok"
    assert payload["pvs1"]["outcome"] == "PVS1"
    assert payload["criterion_assessment"]["criterion"] == "PVS1"
    assert payload["pvs1"]["reasoning_chain"]
