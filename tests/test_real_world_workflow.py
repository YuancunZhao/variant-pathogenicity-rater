from __future__ import annotations

import asyncio
import json

from config import ServerConfig
from server import McpServer, build_registry
from variant_pathogenicity_rater.pipeline.real_world import (
    annotation_to_batch_records,
    run_annotation_batch_workflow,
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


def _context() -> dict[str, object]:
    return {
        "gene": "BRCA1",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
        "phenotype_terms": ["HP:0003002"],
    }


def test_vep_fixture_to_batch_records_to_rate_variant_batch() -> None:
    text = """## ENSEMBL VARIANT EFFECT PREDICTOR
#Uploaded_variation\tSYMBOL\tFeature\tHGVSc\tHGVSp\tConsequence\tEXON\tCANONICAL\tMANE_SELECT\tBIOTYPE\tExisting_variation
17_43092919_A/G\tBRCA1\tNM_007294.4\tNM_007294.4:c.68A>G\tNP_009225.1:p.Glu23Val\tmissense_variant\t2/24\tYES\tYES\tprotein_coding\trs80357713
"""

    result = run_annotation_batch_workflow(
        {
            "annotation_format": "vep",
            "input_text": text,
            "source_version": "vep-fixture-v1",
            "gene_disease_context": _context(),
        }
    )

    converted = result["annotation_to_batch_records"]
    assert converted["record_count"] == 1
    assert converted["records"][0]["annotation_workflow"]["annotation_provenance"][0]["data_source"] == "VEP"
    assert result["succeeded"] == 1
    assert result["results"][0]["classification_result"]["human_review_required"] is True
    assert result["results"][0]["annotation_provenance"][0]["data_source"] == "VEP"
    assert result["results"][0]["normalization_identity"]["normalized_variant_key"] == "17-43092919-A-G"
    assert result["results"][0]["transcript_selection_summary"]["selected_transcript"] == "NM_007294.4"


def test_annovar_fixture_to_batch_records_to_rate_variant_batch() -> None:
    text = """Chr\tStart\tEnd\tRef\tAlt\tGene.refGene\tFunc.refGene\tExonicFunc.refGene\tAAChange.refGene\tavsnp150
17\t43092919\t43092919\tA\tG\tBRCA1\texonic\tnonsynonymous SNV\tBRCA1:NM_007294.4:exon2:c.68A>G:p.Glu23Val\trs80357713
"""

    result = run_annotation_batch_workflow(
        {
            "annotation_format": "annovar",
            "input_text": text,
            "source_version": "annovar-fixture-v1",
            "gene_disease_context": _context(),
        }
    )

    record = result["annotation_to_batch_records"]["records"][0]
    assert record["hgvs_c"] == "NM_007294.4:c.68A>G"
    assert result["succeeded"] == 1
    assert result["results"][0]["annotation_provenance"][0]["data_source"] == "ANNOVAR"
    assert result["results"][0]["normalization_identity"]["normalized_variant_key"] == "17-43092919-A-G"


def test_transcript_ambiguity_preserved() -> None:
    records = [
        {
            "gene": "BRCA1",
            "transcript": "NM_007294.4",
            "hgvs_c": "NM_007294.4:c.68A>G",
            "consequence": "missense_variant",
            "mane_select": "true",
            "transcript_biotype": "protein_coding",
            "chrom": "17",
            "pos": 43092919,
            "ref": "A",
            "alt": "G",
        },
        {
            "gene": "BRCA1",
            "transcript": "NM_007298.3",
            "hgvs_c": "NM_007298.3:c.68A>G",
            "consequence": "missense_variant",
            "mane_select": "true",
            "transcript_biotype": "protein_coding",
            "chrom": "17",
            "pos": 43092919,
            "ref": "A",
            "alt": "G",
        },
    ]

    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": records,
            "gene_disease_context": _context(),
        }
    )

    summary = result["results"][0]["transcript_selection_summary"]
    codes = {flag["code"] for flag in summary["review_flags"]}
    assert result["succeeded"] == 1
    assert len(summary["candidate_transcripts"]) == 2
    assert "TRANSCRIPT_SELECTION_AMBIGUITY" in codes
    assert "MULTIPLE_MANE_SELECT_CONFLICT" in codes


def test_missing_hgvs_becomes_limitation() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": [
                {
                    "gene": "BRCA1",
                    "transcript": "NM_007294.4",
                    "consequence": "missense_variant",
                    "chrom": "17",
                    "pos": 43092919,
                    "ref": "A",
                    "alt": "G",
                }
            ],
            "gene_disease_context": _context(),
        }
    )

    assert result["succeeded"] == 1
    assert any("Missing HGVS" in limitation for limitation in result["limitations"])
    assert any(
        "not directly generate ACMG evidence" in limitation
        for limitation in result["limitations"]
    )


def test_malformed_annotation_row_becomes_failed_record() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "input_text": "gene,transcript,hgvs_c\nBRCA1,NM_007294.4,NM_007294.4:c.68A>G,extra\n",
            "gene_disease_context": _context(),
        }
    )

    assert result["total_records"] == 1
    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["failed_records"][0]["error"]["code"] == "MALFORMED_ANNOTATION_RECORD"


def test_malformed_annotation_row_does_not_shift_success_index() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "input_text": (
                "gene,transcript,hgvs_c,chrom,pos,ref,alt\n"
                "BRCA1,NM_007294.4,NM_007294.4:c.68A>G,17,43092919,A,G,extra\n"
                "BRCA1,NM_007294.4,NM_007294.4:c.68A>G,17,43092919,A,G\n"
            ),
            "gene_disease_context": _context(),
        }
    )

    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert [item["input_index"] for item in result["results"]] == [0, 1]
    assert result["results"][0]["status"] == "error"
    assert result["results"][1]["status"] == "ok"


def test_batch_report_preserves_per_variant_review_flags() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": [
                {
                    "gene": "BRCA1",
                    "transcript": "NM_007294.4",
                    "hgvs_c": "NM_007294.4:c.68A>G",
                    "chrom": "17",
                    "pos": 43092919,
                    "ref": "A",
                    "alt": "G",
                }
            ],
            "gene_disease_context": _context(),
        }
    )

    assert result["results"][0]["review_required"] is True
    assert result["results"][0]["review_flags"]
    assert result["results"][0]["classification_result"]["review_flags"]


def test_annotation_to_batch_records_accepts_parsed_annotations() -> None:
    workflow = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": [
                {
                    "gene": "BRCA1",
                    "transcript": "NM_007294.4",
                    "hgvs_c": "NM_007294.4:c.68A>G",
                    "chrom": "17",
                    "pos": 43092919,
                    "ref": "A",
                    "alt": "G",
                }
            ],
            "gene_disease_context": _context(),
        }
    )
    annotations = workflow["annotation_to_batch_records"]["records"][0]["options"]["annotations"]

    converted = annotation_to_batch_records(
        [],
        failed_records=[],
        options={},
        context=_context(),
    )

    assert annotations
    assert converted["records"] == []
    assert converted["human_review_required"] is True


def test_mcp_rate_annotated_variants_tool_smoke() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 43,
        "method": "tools/call",
        "params": {
            "name": "rate_annotated_variants",
            "arguments": {
                "annotation_format": "generic",
                "records": [
                    {
                        "gene": "BRCA1",
                        "transcript": "NM_007294.4",
                        "hgvs_c": "NM_007294.4:c.68A>G",
                        "chrom": "17",
                        "pos": 43092919,
                        "ref": "A",
                        "alt": "G",
                    }
                ],
                "gene_disease_context": _context(),
            },
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["tool"] == "rate_annotated_variants"
    assert tool_payload["succeeded"] == 1
    assert tool_payload["results"][0]["classification_result"]["human_review_required"] is True


def test_annotation_missing_key_fields_is_captured_and_source_version_missing_warns() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": [{"consequence": "missense_variant"}],
            "gene_disease_context": _context(),
        }
    )

    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["failed_records"][0]["error"]["code"] == "MALFORMED_ANNOTATION_RECORD"
    assert any("source_version is missing" in limitation for limitation in result["limitations"])


def test_annotation_bom_mixed_case_and_unnamed_columns_are_cleaned() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "input_text": (
                "\ufeffGene,Transcript,HGVSc,Chrom,Pos,Ref,Alt,Unnamed: 0\n"
                " brca1 , nm_007294.4 ,NM_007294.4:c.68A%3EG,chr17,43092919,a,g,\n"
            ),
            "source_version": "generic-fixture-v1",
            "gene_disease_context": _context(),
        }
    )

    assert result["succeeded"] == 1
    assert result["results"][0]["normalized_variant_key"] == "17-43092919-A-G"
    assert any("Excel-generated column" in limitation for limitation in result["limitations"])
