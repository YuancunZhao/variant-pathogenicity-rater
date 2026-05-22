from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from variant_pathogenicity_rater.evidence.clinvar import (
    ClinVarProvider,
    ClinVarQuery,
    MockClinVarProvider,
    parse_clinvar_record,
)
from variant_pathogenicity_rater.data_sources.providers import ClinVarOnlineProvider
from variant_pathogenicity_rater.schemas.evidence import EvidenceStrength
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))


def test_clinvar_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        ClinVarProvider()  # type: ignore[abstract]


def test_parse_clinvar_record_contains_required_contract() -> None:
    record = parse_clinvar_record(
        {
            "variation_id": "1",
            "clinical_significance": "Pathogenic",
            "review_status": "reviewed by expert panel",
            "condition": "Example condition",
            "submitter_count": 2,
            "last_evaluated": "2025-01-01",
            "conflicting_interpretations": False,
            "germline_or_somatic": "germline",
            "citations": ["PMID:1"],
        }
    )

    dumped = json.loads(record.model_dump_json())
    assert dumped["variation_id"] == "1"
    assert dumped["condition"] == "Example condition"
    assert dumped["conflicting_interpretations"] is False
    assert dumped["citations"] == ["PMID:1"]
    assert dumped["review_stars"] == 3
    assert dumped["review_confidence"] == "high"


def test_mock_provider_queries_by_gene_and_hgvs_c() -> None:
    result = MockClinVarProvider().query(
        ClinVarQuery(gene="BRCA1", hgvs_c="NM_007294.4:c.68_69delAG")
    )

    assert len(result.records) == 1
    assert result.records[0].variation_id == "17661"
    assert result.candidate_evidence_items[0].code == "PP5"
    assert result.candidate_evidence_items[0].strength == EvidenceStrength.NONE
    assert result.candidate_evidence_items[0].supporting_data["automatic_application"] is False
    assert "PS1" in result.candidate_evidence_items[0].supporting_data["candidate_acmg_codes"]


def test_mock_provider_queries_by_rsid_and_marks_benign_candidate() -> None:
    result = MockClinVarProvider().query(ClinVarQuery(rsid="rs55555"))

    assert len(result.records) == 1
    assert result.records[0].clinical_significance == "Likely benign"
    assert result.candidate_evidence_items[0].code == "BP6"
    assert result.candidate_evidence_items[0].direction == "benign"


def test_mock_provider_queries_by_variation_id_and_flags_conflict() -> None:
    result = MockClinVarProvider().query(ClinVarQuery(variation_id="13961"))

    assert len(result.records) == 1
    assert result.records[0].conflicting_interpretations is True
    assert result.review_flags[0].code == "CLINVAR_CONFLICTING_INTERPRETATIONS"
    assert result.review_flags[0].blocking is True
    assert result.candidate_evidence_items[0].direction == "conflicting"


def test_mock_provider_queries_by_genomic_coordinates() -> None:
    result = MockClinVarProvider().query(
        ClinVarQuery(
            chromosome="7",
            position=117559593,
            ref="CTT",
            alt="C",
            genome_build="GRCh38",
        )
    )

    assert len(result.records) == 1
    assert result.records[0].variation_id == "7108"


def test_mcp_query_clinvar_tool_returns_records_and_candidates() -> None:
    from tools.rate_variant import query_clinvar

    payload = asyncio.run(
        query_clinvar(
            {
                "query": {
                    "gene": "BRCA1",
                    "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
                }
            }
        )
    )

    assert payload["status"] == "ok"
    assert payload["tool"] == "query_clinvar"
    assert payload["clinvar_records"][0]["variation_id"] == "17661"
    assert payload["candidate_evidence_items"][0]["strength"] == "none"
    assert payload["human_review"]["required"] is True


def test_online_provider_requires_explicit_enabled_flag(tmp_path) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
    from variant_pathogenicity_rater.data_sources.providers import ProviderDisabledError

    with pytest.raises(ProviderDisabledError):
        ClinVarOnlineProvider(
            DataSourceConfig(
                name="clinvar",
                mode="online",
                online_enabled=False,
                cache_dir=str(tmp_path),
            )
        )


def test_online_provider_parses_mocked_esummary_and_keeps_candidate_only(tmp_path) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        if endpoint.endswith("esearch.fcgi"):
            assert "BRCA1" in params["term"]
            return {"esearchresult": {"idlist": ["17661"]}}
        return {
            "result": {
                "uids": ["17661"],
                "17661": {
                    "variation_id": "17661",
                    "germline_classification": {
                        "description": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "last_evaluated": "2024-02-03",
                    },
                    "trait_set": [{"trait_name": "Hereditary breast and ovarian cancer"}],
                    "number_submitters": 5,
                    "citations": [{"pmid": "123"}],
                    "classification_type": "germline",
                },
            }
        }

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            source_version="clinvar-test-release",
            parser_version="clinvar-parser-test",
            cache_dir=str(tmp_path),
        ),
        http_get=http_get,
    )
    result = provider.query(
        ClinVarQuery(
            gene="BRCA1",
            hgvs_c="NM_007294.4:c.68_69delAG",
            condition="Hereditary breast and ovarian cancer",
        )
    )

    assert result.records[0].variation_id == "17661"
    assert result.records[0].clinical_significance == "Pathogenic"
    assert result.records[0].review_stars == 3
    assert result.records[0].citations == ["PMID:123"]
    assert result.candidate_evidence_items[0].strength == "none"
    assert result.candidate_evidence_items[0].supporting_data["candidate_only"] is True
    assert result.candidate_evidence_items[0].supporting_data["evidence_status"] == "candidate"
    assert result.candidate_evidence_items[0].supporting_data["applied"] is False
    assert result.candidate_evidence_items[0].supporting_data["automatic_application"] is False
    provenance = result.records[0].source.provenance
    assert provenance.query["gene"] == "BRCA1"
    assert provenance.source_version == "clinvar-test-release"
    assert provenance.raw_record_hash
    assert provenance.parser_version == "clinvar-parser-test"
    assert provenance.source_url.endswith("/17661/")
    assert provenance.review_status == "reviewed by expert panel"
    assert provenance.last_evaluated == "2024-02-03"


def test_online_provider_cache_hit_does_not_repeat_http(tmp_path) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    calls = {"count": 0}

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        calls["count"] += 1
        if endpoint.endswith("esearch.fcgi"):
            return {"esearchresult": {"idlist": ["1"]}}
        return {
            "result": {
                "uids": ["1"],
                "1": {
                    "variation_id": "1",
                    "clinical_significance": {"description": "Likely benign"},
                    "review_status": "criteria provided, single submitter",
                    "condition": "not specified",
                },
            }
        }

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            source_version="cache-test",
            cache_dir=str(tmp_path),
        ),
        http_get=http_get,
    )
    query = ClinVarQuery(rsid="rs55555")

    first = provider.query(query)
    second = provider.query(query)

    assert calls["count"] == 2
    assert first.records[0].variation_id == second.records[0].variation_id == "1"
    assert any("disk cache" in limitation for limitation in second.limitations)


@pytest.mark.parametrize(
    ("case_name", "summary", "expected"),
    [
        (
            "expert panel P/LP",
            {
                "variation_id": "101",
                "germline_classification": {
                    "description": "Likely pathogenic",
                    "review_status": "reviewed by expert panel",
                    "last_evaluated": "2025-05-01",
                },
                "trait_set": [{"trait_name": "Hereditary breast and ovarian cancer"}],
                "number_submitters": 6,
                "citations": [{"pmid": "111"}],
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Likely pathogenic",
                "review_stars": 3,
                "review_confidence": "high",
                "condition": "Hereditary breast and ovarian cancer",
                "citations": ["PMID:111"],
                "germline_or_somatic": "germline",
                "candidate_count": 1,
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flag_codes": set(),
            },
        ),
        (
            "single submitter P/LP",
            {
                "variation_id": "102",
                "clinical_significance": {"description": "Pathogenic"},
                "review_status": "criteria provided, single submitter",
                "condition": "Hereditary breast and ovarian cancer",
                "submitter_count": 1,
                "last_evaluated": "2025-01-01",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Pathogenic",
                "review_stars": 1,
                "review_confidence": "low",
                "candidate_count": 1,
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flag_codes": {"CLINVAR_LOW_REVIEW_CONFIDENCE"},
            },
        ),
        (
            "conflicting interpretations",
            {
                "variation_id": "103",
                "clinical_significance": {"description": "Conflicting interpretations of pathogenicity"},
                "review_status": "criteria provided, conflicting interpretations",
                "condition": "Hereditary breast and ovarian cancer",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Conflicting interpretations of pathogenicity",
                "review_stars": 1,
                "review_confidence": "low",
                "candidate_count": 1,
                "candidate_code": "PP5",
                "direction": "conflicting",
                "flag_codes": {
                    "CLINVAR_CONFLICTING_INTERPRETATIONS",
                    "CLINVAR_LOW_REVIEW_CONFIDENCE",
                },
            },
        ),
        (
            "B/LB",
            {
                "variation_id": "104",
                "clinical_significance": {"description": "Likely benign"},
                "review_status": "criteria provided, multiple submitters, no conflicts",
                "condition": "Hereditary breast and ovarian cancer",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Likely benign",
                "review_stars": 2,
                "review_confidence": "moderate",
                "candidate_count": 1,
                "candidate_code": "BP6",
                "direction": "benign",
                "flag_codes": set(),
            },
        ),
        (
            "VUS",
            {
                "variation_id": "105",
                "clinical_significance": {"description": "Uncertain significance"},
                "review_status": "criteria provided, single submitter",
                "condition": "Hereditary breast and ovarian cancer",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Uncertain significance",
                "review_stars": 1,
                "review_confidence": "low",
                "candidate_count": 0,
                "flag_codes": {"CLINVAR_LOW_REVIEW_CONFIDENCE"},
            },
        ),
        (
            "somatic-only",
            {
                "variation_id": "106",
                "clinical_significance": {"description": "Pathogenic"},
                "review_status": "reviewed by expert panel",
                "condition": "Somatic neoplasm",
                "classification_type": "somatic",
            },
            {
                "clinical_significance": "Pathogenic",
                "review_stars": 3,
                "review_confidence": "high",
                "condition": "Somatic neoplasm",
                "germline_or_somatic": "somatic",
                "candidate_count": 0,
                "flag_codes": {
                    "CLINVAR_NON_GERMLINE_ASSERTION",
                    "CLINVAR_CONDITION_MISMATCH",
                },
            },
        ),
        (
            "no assertion criteria",
            {
                "variation_id": "107",
                "clinical_significance": {"description": "Pathogenic"},
                "review_status": "no assertion criteria provided",
                "condition": "Hereditary breast and ovarian cancer",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Pathogenic",
                "review_stars": 0,
                "review_confidence": "very_low",
                "candidate_count": 1,
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flag_codes": {"CLINVAR_LOW_REVIEW_CONFIDENCE"},
            },
        ),
        (
            "outdated record",
            {
                "variation_id": "108",
                "clinical_significance": {"description": "Pathogenic"},
                "review_status": "criteria provided, single submitter",
                "condition": "Hereditary breast and ovarian cancer",
                "last_evaluated": "2015-01-01",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Pathogenic",
                "review_stars": 1,
                "review_confidence": "low",
                "candidate_count": 1,
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flag_codes": {
                    "CLINVAR_LOW_REVIEW_CONFIDENCE",
                    "CLINVAR_OLD_SUBMISSION",
                },
            },
        ),
        (
            "condition mismatch",
            {
                "variation_id": "109",
                "clinical_significance": {"description": "Pathogenic"},
                "review_status": "reviewed by expert panel",
                "condition": "Unrelated cardiomyopathy",
                "classification_type": "germline",
            },
            {
                "clinical_significance": "Pathogenic",
                "review_stars": 3,
                "review_confidence": "high",
                "condition": "Unrelated cardiomyopathy",
                "candidate_count": 1,
                "candidate_code": "PP5",
                "direction": "pathogenic",
                "flag_codes": {"CLINVAR_CONDITION_MISMATCH"},
            },
        ),
    ],
)
def test_online_provider_parser_and_safety_validation_matrix(
    tmp_path, case_name: str, summary: dict, expected: dict
) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        return {"result": {"uids": [str(summary["variation_id"])], str(summary["variation_id"]): summary}}

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            cache_dir=str(tmp_path / case_name.replace("/", "_")),
        ),
        http_get=http_get,
    )
    result = provider.query(
        ClinVarQuery(
            variation_id=str(summary["variation_id"]),
            condition="Hereditary breast and ovarian cancer",
        )
    )

    record = result.records[0]
    assert record.clinical_significance == expected["clinical_significance"]
    assert record.review_stars == expected["review_stars"]
    assert record.review_confidence == expected["review_confidence"]
    if "condition" in expected:
        assert record.condition == expected["condition"]
    if "citations" in expected:
        assert record.citations == expected["citations"]
    if "germline_or_somatic" in expected:
        assert record.germline_or_somatic == expected["germline_or_somatic"]

    assert len(result.candidate_evidence_items) == expected["candidate_count"]
    for item in result.candidate_evidence_items:
        assert item.strength == EvidenceStrength.NONE
        assert item.supporting_data["candidate_only"] is True
        assert item.supporting_data["evidence_status"] == "candidate"
        assert item.supporting_data["applied"] is False
        assert item.supporting_data["automatic_application"] is False
    if expected["candidate_count"]:
        item = result.candidate_evidence_items[0]
        assert item.code == expected["candidate_code"]
        assert item.direction == expected["direction"]

    flag_codes = {flag.code for flag in result.review_flags}
    assert expected["flag_codes"].issubset(flag_codes)


def test_online_provider_conflict_condition_and_somatic_safety_flags(tmp_path) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        return {
            "result": {
                "uids": ["2"],
                "2": {
                    "variation_id": "2",
                    "clinical_significance": {"description": "Conflicting interpretations"},
                    "review_status": "no assertion criteria provided",
                    "condition": "Somatic neoplasm",
                    "submitter_count": 1,
                    "last_evaluated": "2015-01-01",
                    "classification_type": "somatic",
                },
            }
        }

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            cache_dir=str(tmp_path),
        ),
        http_get=http_get,
    )
    result = provider.query(
        ClinVarQuery(variation_id="2", condition="Hereditary breast and ovarian cancer")
    )

    flag_codes = {flag.code for flag in result.review_flags}
    assert "CLINVAR_CONFLICTING_INTERPRETATIONS" in flag_codes
    assert "CLINVAR_CONDITION_MISMATCH" in flag_codes
    assert "CLINVAR_LOW_REVIEW_CONFIDENCE" in flag_codes
    assert "CLINVAR_OLD_SUBMISSION" in flag_codes
    assert "CLINVAR_NON_GERMLINE_ASSERTION" in flag_codes
    assert result.candidate_evidence_items == []
    assert any("Somatic-only" in limitation for limitation in result.limitations)


@pytest.mark.parametrize(
    ("query", "expected_term"),
    [
        (ClinVarQuery(gene="BRCA1", hgvs_c="NM_007294.4:c.68_69delAG"), "BRCA1[gene]"),
        (ClinVarQuery(rsid="rs80357914"), "80357914[RS]"),
    ],
)
def test_online_provider_query_shapes_use_mocked_esearch(
    tmp_path, query: ClinVarQuery, expected_term: str
) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    calls: list[tuple[str, dict[str, str]]] = []

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        calls.append((endpoint, params))
        if endpoint.endswith("esearch.fcgi"):
            assert expected_term in params["term"]
            return {"esearchresult": {"idlist": ["17661"]}}
        return {
            "result": {
                "uids": ["17661"],
                "17661": {
                    "variation_id": "17661",
                    "clinical_significance": {"description": "Pathogenic"},
                    "review_status": "reviewed by expert panel",
                    "condition": "Hereditary breast and ovarian cancer",
                    "classification_type": "germline",
                },
            }
        }

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            cache_dir=str(tmp_path / expected_term.replace("/", "_")),
        ),
        http_get=http_get,
    )
    result = provider.query(query)

    assert result.records[0].variation_id == "17661"
    assert [call[0].rsplit("/", 1)[-1] for call in calls] == ["esearch.fcgi", "esummary.fcgi"]


def test_online_provider_variation_id_skips_esearch(tmp_path) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    endpoints: list[str] = []

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        endpoints.append(endpoint)
        assert params["id"] == "17661"
        return {
            "result": {
                "uids": ["17661"],
                "17661": {
                    "variation_id": "17661",
                    "clinical_significance": {"description": "Pathogenic"},
                    "review_status": "reviewed by expert panel",
                    "condition": "Hereditary breast and ovarian cancer",
                    "classification_type": "germline",
                },
            }
        }

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            cache_dir=str(tmp_path),
        ),
        http_get=http_get,
    )
    result = provider.query(ClinVarQuery(variation_id="17661"))

    assert result.records[0].variation_id == "17661"
    assert [endpoint.rsplit("/", 1)[-1] for endpoint in endpoints] == ["esummary.fcgi"]


@pytest.mark.parametrize(
    ("query", "http_get", "expected_error"),
    [
        (ClinVarQuery(), lambda endpoint, params: {}, "ValueError"),
        (ClinVarQuery(chromosome="17", position=43092919), lambda endpoint, params: {}, "ValueError"),
        (
            ClinVarQuery(rsid="rs80357914"),
            lambda endpoint, params: (_ for _ in ()).throw(TimeoutError("simulated timeout")),
            "TimeoutError",
        ),
        (ClinVarQuery(rsid="rs80357914"), lambda endpoint, params: [], "AttributeError"),
    ],
)
def test_online_provider_invalid_empty_network_and_malformed_failures_are_limitations(
    tmp_path, query: ClinVarQuery, http_get, expected_error: str
) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            cache_dir=str(tmp_path / expected_error),
        ),
        http_get=http_get,
    )
    result = provider.query(query)

    assert result.records == []
    assert result.candidate_evidence_items == []
    assert any("ClinVar online query failed" in limitation for limitation in result.limitations)
    assert any(expected_error in limitation for limitation in result.limitations)


def test_online_provider_failure_returns_limitation(tmp_path) -> None:
    from variant_pathogenicity_rater.data_sources.config import DataSourceConfig

    def http_get(endpoint: str, params: dict[str, str]) -> dict:
        raise TimeoutError("simulated timeout")

    provider = ClinVarOnlineProvider(
        DataSourceConfig(
            name="clinvar",
            mode="online",
            online_enabled=True,
            cache_dir=str(tmp_path),
        ),
        http_get=http_get,
    )
    result = provider.query(ClinVarQuery(rsid="rs334"))

    assert result.records == []
    assert any("ClinVar online query failed" in limitation for limitation in result.limitations)


def test_rate_variant_with_mocked_online_clinvar_keeps_report_candidate_only(
    tmp_path, monkeypatch
) -> None:
    def http_get(self, endpoint: str, params: dict[str, str]) -> dict:
        if endpoint.endswith("esearch.fcgi"):
            return {"esearchresult": {"idlist": ["17661"]}}
        return {
            "result": {
                "uids": ["17661"],
                "17661": {
                    "variation_id": "17661",
                    "germline_classification": {
                        "description": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "last_evaluated": "2025-05-01",
                    },
                    "trait_set": [{"trait_name": "Hereditary breast and ovarian cancer"}],
                    "number_submitters": 6,
                    "citations": [{"pmid": "111"}],
                    "classification_type": "germline",
                },
            }
        }

    monkeypatch.setattr(ClinVarOnlineProvider, "_http_get", http_get)
    result = rate_variant(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68_69delAG",
            "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
            "chromosome": "17",
            "position": 43092919,
            "ref": "AG",
            "alt": "A",
            "disease": "Hereditary breast and ovarian cancer",
            "inheritance": "autosomal dominant",
            "options": {
                "data_sources": {
                    "clinvar": {
                        "mode": "online",
                        "online_enabled": True,
                        "cache_dir": str(tmp_path),
                        "source_version": "mocked-online-release",
                    }
                }
            },
        }
    )

    clinvar_items = [
        item for item in result["evidence_items"] if item["source"]["name"] == "ClinVar"
    ]
    assert clinvar_items
    assert {item["strength"] for item in clinvar_items} == {"none"}
    assert all(item["supporting_data"]["candidate_only"] is True for item in clinvar_items)
    assert all(item["supporting_data"]["applied"] is False for item in clinvar_items)
    assert all(
        "was not counted because" in limitation
        for limitation in result["classification_result"]["limitations"]
        if limitation.startswith("PP5 evidence ev-clinvar-")
    )

    triggered_section = result["report_text"].split("## Candidate / Review-Note Evidence")[0]
    candidate_section = result["report_text"].split("## Candidate / Review-Note Evidence")[1]
    assert "source: ClinVar" not in triggered_section
    assert "source: ClinVar" in candidate_section


def test_rate_variant_online_clinvar_failure_only_enters_limitations(
    tmp_path, monkeypatch
) -> None:
    def http_get(self, endpoint: str, params: dict[str, str]) -> dict:
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(ClinVarOnlineProvider, "_http_get", http_get)
    result = rate_variant(
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68_69delAG",
            "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
            "chromosome": "17",
            "position": 43092919,
            "ref": "AG",
            "alt": "A",
            "disease": "Hereditary breast and ovarian cancer",
            "inheritance": "autosomal dominant",
            "options": {
                "data_sources": {
                    "clinvar": {
                        "mode": "online",
                        "online_enabled": True,
                        "cache_dir": str(tmp_path),
                    }
                }
            },
        }
    )

    assert result["status"] == "ok"
    assert result["step_results"]["query_clinvar"]["records"] == []
    assert not any(item["source"]["name"] == "ClinVar" for item in result["evidence_items"])
    assert any("ClinVar online query failed" in limitation for limitation in result["limitations"])
