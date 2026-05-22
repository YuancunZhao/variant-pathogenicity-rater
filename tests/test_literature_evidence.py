from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

from variant_pathogenicity_rater.evidence.literature import (
    MockLiteratureProvider,
    extract_literature_evidence,
)
from variant_pathogenicity_rater.schemas import EvidenceStrength, GeneDiseaseContext, Variant


ROOT = Path(__file__).resolve().parents[1]


def _variant() -> Variant:
    return Variant(
        variant_id="GRCh38-1-123-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=123,
        ref="A",
        alt="G",
        gene_symbol="GENE1",
        hgvs_c="NM_000001.1:c.76A>G",
        hgvs_p="NP_000001.1:p.Lys26Arg",
    )


def _context() -> GeneDiseaseContext:
    return GeneDiseaseContext(
        gene_symbol="GENE1",
        disease_name="GENE1-related example disorder",
        phenotype_terms=["HP:0001250", "HP:0001263"],
    )


def _bs3_variant() -> Variant:
    return Variant(
        variant_id="GRCh38-2-200-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="2",
        pos=200,
        ref="A",
        alt="G",
        gene_symbol="GENE2",
        hgvs_c="NM_000002.1:c.100A>G",
        hgvs_p="NP_000002.1:p.Lys34Arg",
    )


def test_mock_literature_provider_returns_citation_preserving_records() -> None:
    result = extract_literature_evidence(_variant(), _context(), MockLiteratureProvider())

    assert len(result.literature_records) == 2
    assert {record.citation for record in result.literature_records} == {
        "PMID:11111111",
        "PMID:22222222",
    }
    assert all(record.requires_review for record in result.literature_records)


def test_literature_extracts_candidate_codes_without_applying_criteria() -> None:
    result = extract_literature_evidence(_variant(), _context())

    codes = {item.code for item in result.candidate_evidence_items}
    assert {"PS3", "PS2", "PM6", "PP1", "PS4", "PP4"}.issubset(codes)
    assert all(item.strength == EvidenceStrength.NONE for item in result.candidate_evidence_items)
    assert all(item.requires_review for item in result.candidate_evidence_items)
    assert all(
        item.supporting_data["automatic_application"] is False
        for item in result.candidate_evidence_items
    )


def test_functional_literature_supports_bs3_candidate_without_applying_it() -> None:
    result = extract_literature_evidence(_bs3_variant(), None)

    assert [item.code for item in result.candidate_evidence_items] == ["BS3"]
    assert result.candidate_evidence_items[0].direction == "benign"
    assert result.candidate_evidence_items[0].strength == EvidenceStrength.NONE
    assert result.candidate_evidence_items[0].supporting_data["citation"] == "PMID:44444444"


def test_literature_deduplicates_same_study_before_candidate_mapping() -> None:
    result = extract_literature_evidence(_variant(), _context())

    assert [record.pmid for record in result.literature_records].count("22222222") == 1
    duplicate_claims = [
        claim for claim in result.extracted_claims if claim.claim_id == "claim-duplicate-gene1"
    ]
    assert duplicate_claims == []


def test_literature_review_flags_capture_mock_and_review_requirements() -> None:
    result = extract_literature_evidence(_variant(), _context())

    flag_codes = {flag.code for flag in result.review_flags}
    assert "LITERATURE_MOCK_PROVIDER" in flag_codes
    assert "LITERATURE_HUMAN_REVIEW_REQUIRED" in flag_codes
    assert "LITERATURE_LOW_QUALITY_EVIDENCE" in flag_codes


def test_search_literature_evidence_mcp_tool_uses_mock_provider() -> None:
    module_path = ROOT / "mcp-server" / "tools" / "rate_variant.py"
    sys.path.insert(0, str(ROOT / "mcp-server"))
    spec = importlib.util.spec_from_file_location("rate_variant_literature_tool", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = asyncio.run(
        module.search_literature_evidence(
            {
                "variant": json.loads(_variant().model_dump_json()),
                "gene_disease_context": json.loads(_context().model_dump_json()),
            }
        )
    )

    assert result["status"] == "ok"
    assert result["stage"] == "mock_literature_evidence_provider"
    assert result["literature_records"][0]["citation"].startswith("PMID:")
    assert result["candidate_evidence_items"][0]["strength"] == "none"
