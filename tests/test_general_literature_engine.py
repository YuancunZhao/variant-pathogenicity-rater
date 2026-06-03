from __future__ import annotations

import asyncio
import json

from config import ServerConfig
from server import McpServer, build_registry
from variant_pathogenicity_rater.cli import main
from variant_pathogenicity_rater.literature_agent import search_and_summarize_literature
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


def _payload(records: list[dict]) -> dict:
    return {
        "gene": "GENE1",
        "variant": "NM_000001.1:c.76A>G",
        "transcript": "NM_000001.1",
        "disease": "GENE1 disorder",
        "inheritance": "autosomal dominant",
        "literature_records": records,
    }


def _record(**overrides) -> dict:
    base = {
        "record_id": "lit-1",
        "pmid": "123456",
        "doi": "10.1234/example",
        "title": "GENE1 literature record",
        "abstract": "GENE1 NM_000001.1:c.76A>G functional assay report.",
        "source": {"name": "local_fixture"},
        "gene": "GENE1",
        "variant": "NM_000001.1:c.76A>G",
        "disease": "GENE1 disorder",
        "evidence_type": "functional",
        "claim": "Validated assay shows reduced function.",
        "assay_validity": "validated",
        "controls_adequate": True,
        "functional_direction": "reduced_function",
        "extraction_confidence": 0.9,
    }
    base.update(overrides)
    return base


def _codes(result: dict) -> set[str]:
    return {item["code"] for item in result["suggested_evidence"]}


def test_offline_fixture_search_preserves_core_record_fields() -> None:
    result = search_and_summarize_literature(_payload([_record()])).model_dump(mode="json")

    record = result["literature_search_results"][0]
    assert record["pmid"] == "123456"
    assert record["doi"] == "10.1234/example"
    assert record["title"] == "GENE1 literature record"
    assert record["abstract"].startswith("GENE1")
    assert record["source"] == "local_fixture"
    assert record["provenance"]["caller_supplied"] is True
    assert result["applied_evidence"] == []
    assert result["final_classification_changed"] is False


def test_functional_abnormal_assay_ps3_candidate_and_normal_function_bs3_candidate() -> None:
    result = search_and_summarize_literature(
        _payload(
            [
                _record(record_id="ps3", functional_direction="reduced_function"),
                _record(
                    record_id="bs3",
                    pmid="123457",
                    functional_direction="normal",
                    claim="Validated assay shows normal function.",
                    abstract="GENE1 variant has normal function in validated assay.",
                ),
            ]
        )
    ).model_dump(mode="json")

    assert {"PS3", "BS3"}.issubset(_codes(result))
    assert all(item["candidate_only"] is True for item in result["evidence_items"])
    assert all(item["applied"] is False for item in result["evidence_items"])
    assert all(item["strength"] == "none" for item in result["evidence_items"])


def test_confirmed_and_unconfirmed_de_novo_ps2_pm6_candidates() -> None:
    result = search_and_summarize_literature(
        _payload(
            [
                _record(
                    record_id="ps2",
                    pmid="200001",
                    evidence_type="de_novo",
                    claim="Confirmed de novo in trio with parentage confirmed.",
                    confirmed_de_novo=True,
                    parentage_confirmed=True,
                ),
                _record(
                    record_id="pm6",
                    pmid="200002",
                    evidence_type="de_novo",
                    claim="De novo reported without parentage confirmation.",
                    de_novo_reported=True,
                ),
            ]
        )
    ).model_dump(mode="json")

    assert {"PS2", "PM6"}.issubset(_codes(result))


def test_segregation_ps4_pm3_pp4_ps1_pm5_pm1_pvs1_candidates_and_summaries() -> None:
    records = [
        _record(
            record_id="pp1",
            pmid="300001",
            evidence_type="segregation",
            claim="Variant cosegregates in a pedigree.",
            segregation_count=4,
            pedigree_context=True,
        ),
        _record(
            record_id="ps4",
            pmid="300002",
            evidence_type="case_control",
            claim="Variant enriched in unrelated cases versus controls.",
            case_control_enrichment=True,
        ),
        _record(
            record_id="pm3",
            pmid="300003",
            evidence_type="trans_observation",
            claim="Compound heterozygous variant confirmed in trans.",
            phase="trans",
        ),
        _record(
            record_id="pp4",
            pmid="300004",
            evidence_type="phenotype_specificity",
            claim="Specific phenotype reported for GENE1 disorder.",
        ),
        _record(
            record_id="ps1",
            pmid="300005",
            evidence_type="same_amino_acid",
            claim="Same amino acid pathogenic variant reported.",
            residue_relationship="same_amino_acid",
        ),
        _record(
            record_id="pm5",
            pmid="300006",
            evidence_type="same_residue",
            claim="Same residue different missense pathogenic variant reported.",
            residue_relationship="same_residue_different_missense",
        ),
        _record(
            record_id="pm1",
            pmid="300007",
            evidence_type="hotspot",
            claim="Variant lies in a mutational hotspot critical domain.",
        ),
        _record(
            record_id="pvs1",
            pmid="300008",
            evidence_type="lof_mechanism",
            claim="GENE1 disease mechanism is loss of function with NMD.",
        ),
    ]

    result = search_and_summarize_literature(_payload(records)).model_dump(mode="json")

    assert {"PP1", "PS4", "PM3", "PP4", "PS1", "PM5", "PM1", "PVS1"}.issubset(_codes(result))
    by_criterion = {item["criterion"]: item for item in result["criterion_summaries"]}
    assert by_criterion["PM1"]["evidence_domain"] == "hotspot_or_domain"
    assert by_criterion["PVS1"]["evidence_domain"] == "lof_nmd_mechanism"
    assert by_criterion["PVS1"]["suggested_strength"] == "none"
    assert any("mechanism support only" in item for item in by_criterion["PVS1"]["limitations"])


def test_duplicate_publications_and_families_collapse() -> None:
    result = search_and_summarize_literature(
        _payload(
            [
                _record(record_id="first", pmid="400001", duplicate_study_group="family-a"),
                _record(record_id="second", pmid="400002", duplicate_study_group="family-a"),
            ]
        )
    ).model_dump(mode="json")

    assert len(result["literature_search_results"]) == 1
    assert result["duplicate_groups"][0]["kept_record_id"] == "first"
    assert result["duplicate_groups"][0]["duplicate_record_ids"] == ["second"]


def test_variant_and_disease_mismatch_blocking_flags() -> None:
    result = search_and_summarize_literature(
        _payload(
            [
                _record(
                    variant="NM_000001.1:c.77A>G",
                    disease="Other disorder",
                    variant_match_level="mismatch",
                    disease_match_level="mismatch",
                )
            ]
        )
    ).model_dump(mode="json")

    codes = {flag["code"] for flag in result["blocking_flags"]}
    assert "LITERATURE_VARIANT_MISMATCH" in codes
    assert "LITERATURE_DISEASE_MISMATCH" in codes


def test_abstract_only_limitation_low_confidence_review_flag_and_malformed_record_limitation() -> None:
    result = search_and_summarize_literature(
        _payload(
            [
                _record(extraction_confidence=0.4),
                {"pmid": "missing-title-and-text"},
            ]
        )
    ).model_dump(mode="json")

    assert any("abstract-only" in item for item in result["limitations"])
    assert "LITERATURE_LOW_EXTRACTION_CONFIDENCE" in {flag["code"] for flag in result["review_flags"]}
    assert any("could not be normalized" in item for item in result["limitations"])


def test_candidate_literature_does_not_alter_classification_and_drafts_are_non_applied() -> None:
    base_payload = {
        "gene": "GENE1",
        "transcript": "NM_000001.1",
        "hgvs_c": "NM_000001.1:c.76A>G",
        "chromosome": "1",
        "position": 123,
        "ref": "A",
        "alt": "G",
        "disease": "GENE1 disorder",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
        },
    }
    baseline = rate_variant(base_payload)
    result = search_and_summarize_literature(_payload([_record()])).model_dump(mode="json")
    with_drafts = rate_variant({**base_payload, "reviewed_evidence": result["reviewed_evidence_drafts"]})

    assert result["final_classification_changed"] is False
    assert result["reviewed_evidence_drafts"][0]["evidence_status"] == "needs_more_info"
    assert result["reviewed_evidence_drafts"][0]["requires_manual_review"] is True
    assert with_drafts["final_classification"] == baseline["final_classification"]
    assert with_drafts["applied_evidence"] == []


def test_mcp_search_and_summarize_literature_smoke() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 71,
        "method": "tools/call",
        "params": {
            "name": "search_and_summarize_literature",
            "arguments": _payload([_record()]),
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["tool"] == "search_and_summarize_literature"
    assert payload["status"] == "ok"
    assert payload["suggested_evidence"][0]["candidate_only"] is True
    assert payload["applied_evidence"] == []


def test_cli_literature_search_smoke(tmp_path, capsys) -> None:
    records_path = tmp_path / "records.json"
    records_path.write_text(json.dumps([_record()]), encoding="utf-8")

    exit_code = main(
        [
            "literature-search",
            "--gene",
            "GENE1",
            "--variant",
            "NM_000001.1:c.76A>G",
            "--disease",
            "GENE1 disorder",
            "--literature-records",
            str(records_path),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["tool"] == "search_and_summarize_literature"
    assert payload["final_classification_changed"] is False
