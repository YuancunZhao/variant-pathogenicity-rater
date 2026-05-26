from __future__ import annotations

import asyncio
import json

from config import ServerConfig
from server import McpServer, build_registry
from variant_pathogenicity_rater.clingen_erepo import (
    ClinGenERepoQuery,
    MockClinGenERepoProvider,
)
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.clingen_erepo.provider import (
    ClinGenERepoOnlineProvider,
    LocalFileClinGenERepoProvider,
)
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord, EvidenceSource
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


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
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43092919,
        "ref": "AG",
        "alt": "A",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
        "options": {
            "include_population": False,
            "include_computational": False,
            "include_clinvar": False,
            "include_literature": False,
            "include_clingen_erepo": True,
        },
    }
    payload.update(overrides)
    return payload


def _variant() -> Variant:
    return Variant.model_validate(rate_variant(_payload())["normalized_variant"])


def _context(disease: str = "Hereditary breast and ovarian cancer") -> GeneDiseaseContext:
    return GeneDiseaseContext(gene_symbol="BRCA1", disease_name=disease)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "record_id": "erepo-test",
        "gene": "BRCA1",
        "ca_id": "CA123",
        "clinvar_variation_id": "555",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "genomic": {
            "genome_build": "GRCh38",
            "chromosome": "17",
            "position": 43092919,
            "ref": "AG",
            "alt": "A",
        },
        "disease_condition": "Hereditary breast and ovarian cancer",
        "vcep_name": "BRCA1 VCEP",
        "classification": "Pathogenic",
        "classification_date": "2025-01-15",
        "classification_version": "v1",
        "criteria_applied": [{"criterion": "PVS1", "strength": "very_strong"}],
        "evidence_summaries": [{"summary_text": "VCEP curated summary."}],
        "source_url": "https://erepo.clinicalgenome.org/evrepo/uuid/erepo-test",
        "api_endpoint": "https://erepo.clinicalgenome.org/evrepo/api/classifications",
    }
    record.update(overrides)
    return record


def test_exact_ca_id_match_and_draft() -> None:
    variant = _variant()
    query = ClinGenERepoQuery.from_variant(variant, _context(), ca_id="CA123")

    result = MockClinGenERepoProvider([_record()]).query(
        query,
        variant=variant,
        context=_context(),
    )

    assert result.matches[0].match_level == "exact_variant"
    assert result.matches[0].confidence >= 0.8
    assert result.reviewed_evidence_drafts[0].evidence_status == "needs_more_info"
    assert result.reviewed_evidence_drafts[0].source_candidate_evidence_id


def test_pipeline_erepo_items_remain_candidate_only_and_not_applied() -> None:
    result = rate_variant(
        _payload(
            options={
                **_payload()["options"],
                "clingen_erepo_query": {"ca_id": "CA123"},
                "clingen_erepo_records": [_record()],
            }
        )
    )

    erepo_items = [
        item
        for item in result["evidence_items"]
        if item["source"]["name"] == "ClinGen Evidence Repository"
    ]

    assert erepo_items
    assert all(item["strength"] == "none" for item in erepo_items)
    assert all(item["candidate_only"] is True for item in erepo_items)
    assert all(item["applied"] is False for item in erepo_items)
    assert all(item["supporting_data"]["candidate_only"] is True for item in erepo_items)
    assert all(item["supporting_data"]["applied"] is False for item in erepo_items)
    assert not any(
        item["source"]["name"] == "ClinGen Evidence Repository"
        for item in result["applied_evidence"]
    )


def test_clinvar_variation_id_and_genomic_matches() -> None:
    variant = _variant()

    variation_result = MockClinGenERepoProvider([_record(ca_id=None)]).query(
        ClinGenERepoQuery.from_variant(variant, _context(), clinvar_variation_id="555"),
        variant=variant,
        context=_context(),
    )
    genomic_result = MockClinGenERepoProvider([_record(ca_id=None, clinvar_variation_id=None)]).query(
        ClinGenERepoQuery.from_variant(variant, _context()),
        variant=variant,
        context=_context(),
    )

    assert variation_result.matches[0].matched_identifiers == ["clinvar_variation_id"]
    assert genomic_result.matches[0].matched_identifiers == ["genomic_key"]


def test_gene_only_signal_is_not_variant_match() -> None:
    variant = _variant()
    result = MockClinGenERepoProvider(
        [_record(ca_id=None, clinvar_variation_id=None, hgvs_c=None, hgvs_p=None, genomic={})]
    ).query(ClinGenERepoQuery(gene="BRCA1"), variant=variant, context=_context())

    assert result.matches[0].match_level == "same_gene"
    assert result.vcep_signals[0].signal_type == "gene_level_vcep_activity"
    assert any("does not mean this variant" in item for item in result.vcep_signals[0].limitations)
    assert result.reviewed_evidence_drafts == []


def test_protein_only_candidate_match() -> None:
    variant = _variant()
    result = MockClinGenERepoProvider(
        [_record(ca_id=None, clinvar_variation_id=None, hgvs_c="NM_007294.4:c.999A>G", genomic={})]
    ).query(ClinGenERepoQuery(gene="BRCA1", hgvs_p=variant.hgvs_p), variant=variant, context=_context())

    assert result.matches[0].match_level == "same_protein"
    assert any(flag.code == "CLINGEN_EREPO_PROTEIN_ONLY_MATCH" for flag in result.review_flags)
    assert result.reviewed_evidence_drafts == []


def test_protein_only_pipeline_output_is_review_note_only() -> None:
    result = rate_variant(
        _payload(
            options={
                **_payload()["options"],
                "clingen_erepo_query": {"hgvs_p": "NP_009225.1:p.Glu23ValfsTer17"},
                "clingen_erepo_records": [
                    _record(
                        ca_id=None,
                        clinvar_variation_id=None,
                        hgvs_c="NM_007294.4:c.999A>G",
                        genomic={},
                    )
                ],
            }
        )
    )

    erepo_items = [
        item
        for item in result["review_note_evidence"]
        if item["source"]["name"] == "ClinGen Evidence Repository"
    ]

    assert erepo_items
    assert erepo_items[0]["strength"] == "none"
    assert erepo_items[0]["supporting_data"]["match_level"] == "same_protein"
    assert result["clingen_erepo_reviewed_evidence_drafts"] == []
    assert not any(
        item["source"]["name"] == "ClinGen Evidence Repository"
        for item in result["applied_evidence"]
    )


def test_condition_mismatch_blocks_high_confidence_exact_match() -> None:
    variant = _variant()
    result = MockClinGenERepoProvider(
        [_record(disease_condition="Different condition")]
    ).query(ClinGenERepoQuery.from_variant(variant, _context()), variant=variant, context=_context())

    assert result.matches[0].match_level == "no_match"
    assert result.matches[0].confidence <= 0.3
    assert any(flag.code == "CLINGEN_EREPO_CONDITION_MISMATCH" for flag in result.review_flags)
    assert result.reviewed_evidence_drafts == []


def test_transcript_mismatch_and_stale_classification_flags() -> None:
    variant = _variant()
    result = MockClinGenERepoProvider(
        [_record(hgvs_c="NM_000000.1:c.68_69delAG", transcript="NM_000000.1", classification_date="2019-01-01")]
    ).query(ClinGenERepoQuery.from_variant(variant, _context()), variant=variant, context=_context())

    assert any(flag.code == "CLINGEN_EREPO_TRANSCRIPT_MISMATCH" for flag in result.review_flags)
    assert any(flag.code == "CLINGEN_EREPO_STALE_OR_UNVERSIONED" for flag in result.review_flags)


def test_conflicting_clinvar_and_erepo_classifications_are_review_flagged() -> None:
    variant = _variant()
    clinvar = ClinVarRecord(
        source=EvidenceSource(name="ClinVar", version="test"),
        variation_id="555",
        gene_symbol="BRCA1",
        clinical_significance="Benign",
    )

    result = MockClinGenERepoProvider([_record(classification="Pathogenic")]).query(
        ClinGenERepoQuery.from_variant(variant, _context(), ca_id="CA123"),
        variant=variant,
        context=_context(),
        clinvar_records=[clinvar],
    )

    assert any(flag.code == "CLINGEN_EREPO_CLINVAR_CONFLICT" for flag in result.review_flags)


def test_pipeline_erepo_does_not_alter_classification_and_report_includes_section() -> None:
    without_erepo = rate_variant(_payload(options={**_payload()["options"], "include_clingen_erepo": False}))
    with_erepo = rate_variant(
        _payload(
            options={
                **_payload()["options"],
                "clingen_erepo_query": {"ca_id": "CA123"},
                "clingen_erepo_records": [_record()],
            }
        )
    )

    assert with_erepo["final_classification"] == without_erepo["final_classification"]
    assert with_erepo["applied_evidence"] == without_erepo["applied_evidence"]
    assert "query_clingen_erepo" in with_erepo["step_results"]
    assert with_erepo["clingen_erepo_reviewed_evidence_drafts"][0]["evidence_status"] == "needs_more_info"
    assert "## ClinGen Evidence Repository Match" in with_erepo["report_text"]
    assert "not automatically applied" in with_erepo["report_text"]
    assert "not counted as applied ACMG evidence" in with_erepo["report_text"]
    assert not any(
        item["source"]["name"] == "ClinGen Evidence Repository"
        for item in with_erepo["applied_evidence"]
    )


def test_local_file_provider_csv(tmp_path) -> None:
    path = tmp_path / "erepo.csv"
    path.write_text(
        "record_id,gene,ca_id,disease_condition,classification,classification_date,classification_version,source_url\n"
        "erepo-csv,BRCA1,CA123,Hereditary breast and ovarian cancer,Pathogenic,2025-01-15,v1,https://erepo.example/erepo-csv\n",
        encoding="utf-8",
    )
    variant = _variant()
    provider = LocalFileClinGenERepoProvider(
        DataSourceConfig(name="clingen_erepo", mode=ProviderMode.LOCAL_FILE, local_file=str(path))
    )

    result = provider.query(
        ClinGenERepoQuery.from_variant(variant, _context(), ca_id="CA123"),
        variant=variant,
        context=_context(),
    )

    assert result.records[0].record_id == "erepo-csv"
    assert result.matches[0].match_level == "exact_variant"


def test_online_failure_to_limitation() -> None:
    variant = _variant()
    provider = ClinGenERepoOnlineProvider(
        DataSourceConfig(
            name="clingen_erepo",
            mode=ProviderMode.ONLINE,
            online_enabled=True,
        ),
        http_get=lambda _endpoint, _params: (_ for _ in ()).throw(RuntimeError("offline test")),
    )

    result = provider.query(ClinGenERepoQuery.from_variant(variant, _context()), variant=variant, context=_context())

    assert result.records == []
    assert any("online query failed" in item for item in result.limitations)


def test_mcp_query_clingen_erepo_tool_smoke() -> None:
    variant = json.loads(_variant().model_dump_json())
    request = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {
            "name": "query_clingen_erepo",
            "arguments": {
                "variant": variant,
                "gene_disease_context": _context().model_dump(mode="json"),
                "ca_id": "CA123",
                "clingen_erepo_records": [_record()],
            },
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    payload = json.loads(response["result"]["content"][0]["text"])

    assert payload["status"] == "ok"
    assert payload["records"] == payload["erepo_records"]
    assert payload["matches"][0]["match_level"] == "exact_variant"
    assert payload["reviewed_evidence_drafts"][0]["evidence_status"] == "needs_more_info"


def test_cli_and_mcp_clingen_erepo_record_fields_are_consistent(capsys, tmp_path) -> None:
    from variant_pathogenicity_rater.cli import main

    erepo = tmp_path / "erepo.tsv"
    erepo.write_text(
        "record_id\tgene\tca_id\thgvs_c\tdisease_condition\tclassification\tclassification_date\tclassification_version\tsource_url\n"
        "erepo-cli\tBRCA1\tCA123\tNM_007294.4:c.68_69delAG\tHereditary breast and ovarian cancer\tPathogenic\t2025-01-15\tv1\thttps://erepo.example/erepo-cli\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "rate",
            "--gene",
            "BRCA1",
            "--transcript",
            "NM_007294.4",
            "--hgvs-c",
            "NM_007294.4:c.68_69delAG",
            "--hgvs-p",
            "NP_009225.1:p.Glu23ValfsTer17",
            "--chromosome",
            "17",
            "--position",
            "43092919",
            "--ref",
            "AG",
            "--alt",
            "A",
            "--disease",
            "Hereditary breast and ovarian cancer",
            "--inheritance",
            "autosomal dominant",
            "--include-clingen-erepo",
            "--clingen-erepo-local-file",
            str(erepo),
        ]
    )
    cli_payload = json.loads(capsys.readouterr().out)

    request = {
        "jsonrpc": "2.0",
        "id": 100,
        "method": "tools/call",
        "params": {
            "name": "query_clingen_erepo",
            "arguments": {
                "variant": json.loads(_variant().model_dump_json()),
                "gene_disease_context": _context().model_dump(mode="json"),
                "ca_id": "CA123",
                "clingen_erepo_records": [_record(record_id="erepo-cli", ca_id="CA123")],
            },
        },
    }
    mcp_response = asyncio.run(_server().handle_message(json.dumps(request)))
    mcp_payload = json.loads(mcp_response["result"]["content"][0]["text"])

    assert exit_code == 0
    for field in [
        "records",
        "matches",
        "vcep_signals",
        "reviewed_evidence_drafts",
        "review_flags",
        "limitations",
        "provenance",
    ]:
        assert field in cli_payload["clingen_erepo"]
        assert field in mcp_payload
