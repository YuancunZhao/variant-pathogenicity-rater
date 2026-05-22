from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.providers import build_literature_provider
from variant_pathogenicity_rater.evidence.literature import (
    LiteratureQuery,
    MockLiteratureProvider,
    extract_literature_evidence,
)
from variant_pathogenicity_rater.schemas import (
    ACMGClassification,
    EvidenceStrength,
    GeneDiseaseContext,
    Variant,
)


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


def test_literature_safety_schema_preserves_candidate_fields_and_provenance() -> None:
    result = extract_literature_evidence(_variant(), _context(), MockLiteratureProvider())
    item = next(
        evidence
        for evidence in result.candidate_evidence_items
        if evidence.supporting_data["evidence_type_candidate"] == "PS3_candidate"
    )
    claim = item.supporting_data["extracted_claim"]

    assert item.supporting_data["article_id"] == "11111111"
    assert item.supporting_data["title"]
    assert item.supporting_data["citation"] == "PMID:11111111"
    assert item.source.provenance is not None
    assert claim["evidence_type_candidate"] == "PS3_candidate"
    assert "evidence_quality" in item.supporting_data
    assert "assay_type" in item.supporting_data
    assert "phenotype_match" in item.supporting_data
    assert "condition_match" in item.supporting_data
    assert "variant_match_level" in item.supporting_data
    assert "duplicate_study_group" in item.supporting_data
    assert "extraction_confidence" in item.supporting_data


def test_candidate_type_gates_do_not_auto_apply_requested_literature_codes() -> None:
    result = extract_literature_evidence(_variant(), _context())
    by_candidate_type = {
        item.supporting_data["evidence_type_candidate"]: item
        for item in result.candidate_evidence_items
    }

    for candidate_type in {
        "PS3_candidate",
        "PS2_candidate",
        "PM6_candidate",
        "PP1_candidate",
        "PS4_candidate",
        "PP4_candidate",
    }:
        item = by_candidate_type[candidate_type]
        assert item.strength == EvidenceStrength.NONE
        assert item.supporting_data["candidate_only"] is True
        assert item.supporting_data["automatic_application"] is False
        assert item.supporting_data["human_review_required"] is True


@pytest.mark.parametrize(
    ("evidence_type", "candidate_codes", "expected_candidate_types"),
    [
        ("functional", ["PS3"], ["PS3_candidate"]),
        ("segregation", ["PP1"], ["PP1_candidate"]),
        ("de_novo", ["PS2", "PM6"], ["PS2_candidate", "PM6_candidate"]),
        ("case_report", ["PS4"], ["PS4_candidate"]),
    ],
)
def test_single_paper_maps_only_to_expected_candidate_type(
    evidence_type: str,
    candidate_codes: list[str],
    expected_candidate_types: list[str],
) -> None:
    records = [
        {
            "study_id": f"study-{evidence_type}",
            "pmid": "99000001",
            "citation": "PMID:99000001",
            "title": f"Single {evidence_type} paper",
            "gene": "GENE1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "finding": "Candidate evidence was reported.",
            "claims": [
                {
                    "evidence_type": evidence_type,
                    "candidate_codes": candidate_codes,
                    "direction": "pathogenic",
                    "description": f"{evidence_type} candidate claim.",
                    "extraction_confidence": 0.9,
                    "variant_match_level": "exact",
                    "condition_match": True,
                }
            ],
        }
    ]

    result = extract_literature_evidence(_variant(), _context(), MockLiteratureProvider(records))

    assert [
        item.supporting_data["evidence_type_candidate"]
        for item in result.candidate_evidence_items
    ] == expected_candidate_types
    assert all(item.strength == EvidenceStrength.NONE for item in result.candidate_evidence_items)


def test_literature_deduplicates_same_study_before_candidate_mapping() -> None:
    result = extract_literature_evidence(_variant(), _context())

    assert [record.pmid for record in result.literature_records].count("22222222") == 1
    duplicate_claims = [
        claim for claim in result.extracted_claims if claim.claim_id == "claim-duplicate-gene1"
    ]
    assert duplicate_claims == []


def test_literature_deduplicates_duplicate_study_group() -> None:
    records = [
        {
            "study_id": "pub-a",
            "pmid": "90000001",
            "duplicate_study_group": "shared-family-1",
            "citation": "PMID:90000001",
            "title": "First publication of a shared family",
            "gene": "GENE1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "finding": "Segregation was reported.",
            "claims": [
                {
                    "evidence_type": "segregation",
                    "candidate_codes": ["PP1"],
                    "direction": "pathogenic",
                    "description": "Shared family segregation claim.",
                    "extraction_confidence": 0.8,
                    "variant_match_level": "exact",
                    "condition_match": True,
                }
            ],
        },
        {
            "study_id": "pub-b",
            "pmid": "90000002",
            "duplicate_study_group": "shared-family-1",
            "citation": "PMID:90000002",
            "title": "Second publication of the same family",
            "gene": "GENE1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "finding": "Same family was republished.",
            "claims": [
                {
                    "evidence_type": "segregation",
                    "candidate_codes": ["PP1"],
                    "direction": "pathogenic",
                    "description": "Duplicate family segregation claim.",
                    "extraction_confidence": 0.8,
                    "variant_match_level": "exact",
                    "condition_match": True,
                }
            ],
        },
    ]

    result = extract_literature_evidence(_variant(), _context(), MockLiteratureProvider(records))

    assert len(result.literature_records) == 1
    assert len(result.candidate_evidence_items) == 1
    assert result.candidate_evidence_items[0].supporting_data["duplicate_study_group"] == (
        "shared-family-1"
    )


def test_literature_mismatch_and_low_confidence_set_review_flags() -> None:
    records = [
        {
            "study_id": "pmid-90000003",
            "pmid": "90000003",
            "citation": "PMID:90000003",
            "title": "Condition and variant mismatch example",
            "gene": "GENE1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "finding": "Claim was extracted with uncertain matching.",
            "claims": [
                {
                    "evidence_type": "case_report",
                    "candidate_codes": ["PS4"],
                    "direction": "pathogenic",
                    "description": "Case report for a related but mismatched context.",
                    "condition_match": False,
                    "variant_match_level": "gene_only",
                    "extraction_confidence": 0.4,
                }
            ],
        }
    ]

    result = extract_literature_evidence(_variant(), _context(), MockLiteratureProvider(records))
    flag_codes = {
        flag.code
        for item in result.candidate_evidence_items
        for flag in item.review_flags
    }

    assert "LITERATURE_CONDITION_MISMATCH" in flag_codes
    assert "LITERATURE_VARIANT_MISMATCH" in flag_codes
    assert "LITERATURE_LOW_EXTRACTION_CONFIDENCE" in flag_codes
    assert "LITERATURE_MATCH_OR_CONFIDENCE_REVIEW" in {flag.code for flag in result.review_flags}


def test_local_file_literature_provider_reads_jsonl_and_queries_by_pmid(tmp_path) -> None:
    local_file = tmp_path / "literature.jsonl"
    local_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "study_id": "pmid-91000001",
                        "pmid": "91000001",
                        "citation": "PMID:91000001",
                        "title": "Local JSONL functional paper",
                        "journal": "Offline Fixtures",
                        "year": 2026,
                        "gene": "GENE1",
                        "hgvs_c": "NM_000001.1:c.76A>G",
                        "finding": "Functional abnormality was reported.",
                        "claims": [
                            {
                                "evidence_type": "functional",
                                "candidate_codes": ["PS3"],
                                "direction": "pathogenic",
                                "description": "Local file functional claim.",
                                "assay_type": "enzyme_activity",
                                "extraction_confidence": 0.9,
                                "condition_match": True,
                                "variant_match_level": "exact",
                            }
                        ],
                    }
                )
            ]
        ),
        encoding="utf-8",
    )
    provider = build_literature_provider(
        DataSourceConfig(
            name="literature",
            mode="local_file",
            source_version="local-literature-test",
            parser_version="literature-parser-test",
            cache_dir=str(tmp_path / "cache"),
            local_file=str(local_file),
        )
    )

    records = provider.search(LiteratureQuery(pmid="91000001"))

    assert len(records) == 1
    assert records[0].pmid == "91000001"
    assert records[0].journal == "Offline Fixtures"
    assert records[0].source.provenance.parser_version == "literature-parser-test"


def test_literature_candidate_evidence_does_not_change_classification() -> None:
    result = extract_literature_evidence(_variant(), _context())

    baseline = classify_acmg([], _variant(), _context())
    with_literature = classify_acmg(result.candidate_evidence_items, _variant(), _context())

    assert baseline.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert with_literature.final_classification == baseline.final_classification
    assert with_literature.applied_combination_rule == baseline.applied_combination_rule


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
