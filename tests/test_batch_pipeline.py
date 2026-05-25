from __future__ import annotations

import asyncio
import json

from server import McpServer, build_registry
from config import ServerConfig
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch


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


def _record(**overrides: object) -> dict:
    record = {
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
        "phenotype": ["HP:0003002"],
    }
    record.update(overrides)
    return record


def test_json_batch_success() -> None:
    result = rate_variant_batch({"input_format": "json", "input_text": json.dumps([_record()])})

    assert result["total_records"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    assert result["results"][0]["classification_result"]["human_review_required"] is True


def test_jsonl_batch_success() -> None:
    text = "\n".join([json.dumps(_record()), json.dumps(_record(position=43092920, ref="A", alt="G"))])

    result = rate_variant_batch({"input_format": "jsonl", "input_text": text})

    assert result["total_records"] == 2
    assert result["succeeded"] == 2
    assert result["failed"] == 0


def test_csv_and_tsv_batch_success() -> None:
    csv_result = rate_variant_batch(
        {
            "input_format": "csv",
            "input_text": (
                "gene,transcript,hgvs_c,chromosome,position,ref,alt,disease\n"
                "BRCA1,NM_007294.4,NM_007294.4:c.68A>G,17,43092919,A,G,HBOC\n"
            ),
        }
    )
    tsv_result = rate_variant_batch(
        {
            "input_format": "tsv",
            "input_text": (
                "gene\ttranscript\thgvs_c\tchromosome\tposition\tref\talt\tdisease\n"
                "BRCA1\tNM_007294.4\tNM_007294.4:c.68A>G\t17\t43092919\tA\tG\tHBOC\n"
            ),
        }
    )

    assert csv_result["succeeded"] == 1
    assert tsv_result["succeeded"] == 1


def test_vcf_like_minimal_parsing() -> None:
    result = rate_variant_batch(
        {
            "input_format": "vcf_like",
            "input_text": "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n17\t43092919\t.\tA\tG\t.\t.\t.",
        }
    )

    assert result["succeeded"] == 1
    assert result["results"][0]["normalized_variant_key"] == "17-43092919-A-G"


def test_malformed_row_captured() -> None:
    result = rate_variant_batch(
        {
            "input_format": "jsonl",
            "input_text": json.dumps(_record()) + "\n" + "{bad json",
        }
    )

    assert result["total_records"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert result["failed_records"][0]["error"]["code"] == "MALFORMED_RECORD"


def test_one_bad_record_does_not_stop_batch() -> None:
    result = rate_variant_batch({"records": [_record(), {"gene": "BAD"}]})

    assert result["total_records"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert [item["status"] for item in result["results"]] == ["ok", "error"]


def test_unsupported_variant_captured() -> None:
    result = rate_variant_batch({"records": [_record(variant_type="cnv", alt="<DEL>")]})

    assert result["succeeded"] == 0
    assert result["failed"] == 1
    assert result["failed_records"][0]["error"]["code"] == "UNSUPPORTED_VARIANT_TYPE"


def test_duplicate_warning() -> None:
    result = rate_variant_batch({"records": [_record(), _record()]})

    assert result["succeeded"] == 2
    assert any("Duplicate variant detected" in warning for warning in result["warnings"])
    assert result["summary"]["duplicate_warnings"]


def test_per_record_review_flags_preserved() -> None:
    result = rate_variant_batch(
        {
            "records": [
                _record(
                    options={
                        "include_transcript_selection": True,
                        "annotations": [],
                    }
                )
            ]
        }
    )

    assert result["results"][0]["review_required"] is True
    assert result["results"][0]["review_flags"]


def test_mcp_batch_tool_smoke() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {
            "name": "rate_variant_batch",
            "arguments": {"records": [_record()]},
        },
    }

    response = asyncio.run(_server().handle_message(json.dumps(request)))
    tool_payload = json.loads(response["result"]["content"][0]["text"])

    assert tool_payload["batch_id"]
    assert tool_payload["succeeded"] == 1
    assert tool_payload["results"][0]["classification_result"]["human_review_required"] is True


def test_bom_csv_mixed_case_columns_excel_unnamed_column() -> None:
    result = rate_variant_batch(
        {
            "input_format": "csv",
            "input_text": (
                "\ufeffGene,Transcript,HGVSc,Chromosome,Position,Ref,Alt,Unnamed: 8,Disease\n"
                " brca1 , nm_007294.4 ,NM_007294.4:c.68A>G,chr17,43092919,a,g,,HBOC\n"
            ),
        }
    )

    assert result["succeeded"] == 1
    assert result["results"][0]["normalized_variant_key"] == "17-43092919-A-G"
    assert any("Excel-generated column" in warning for warning in result["warnings"])
    assert any("uppercased" in warning for warning in result["warnings"])


def test_csv_empty_and_comment_lines_are_ignored() -> None:
    result = rate_variant_batch(
        {
            "input_format": "csv",
            "input_text": (
                "\ufeff# exported by spreadsheet\n"
                "\n"
                "gene,transcript,hgvs_c,chromosome,position,ref,alt,disease\r\n"
                "BRCA1,NM_007294.4,NM_007294.4:c.68A>G,17,43092919,A,G,HBOC\r"
            ),
        }
    )

    assert result["total_records"] == 1
    assert result["succeeded"] == 1


def test_jsonl_one_malformed_line_continues() -> None:
    result = rate_variant_batch(
        {
            "input_format": "jsonl",
            "input_text": "\n".join(
                [
                    "# comment",
                    json.dumps(_record()),
                    "{not json}",
                    json.dumps(_record(position=43092920, ref="A", alt="G")),
                ]
            ),
        }
    )

    assert result["total_records"] == 3
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["failed_records"][0]["error"]["code"] == "MALFORMED_RECORD"


def test_vcf_extra_columns_are_accepted_but_symbolic_and_multiallelic_alt_rejected() -> None:
    ok = rate_variant_batch(
        {
            "input_format": "vcf",
            "input_text": (
                "##fileformat=VCFv4.2\n"
                "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tS1\n"
                "chr17\t43092919\t.\ta\tg\t.\tPASS\tDP=10\tGT\t0/1\n"
            ),
        }
    )
    symbolic = rate_variant_batch(
        {
            "input_format": "vcf_like",
            "input_text": "#CHROM\tPOS\tID\tREF\tALT\n17\t43092919\t.\tA\t<DEL>\n",
        }
    )
    multiallelic = rate_variant_batch(
        {
            "input_format": "vcf_like",
            "input_text": "#CHROM\tPOS\tID\tREF\tALT\n17\t43092919\t.\tA\tG,T\n",
        }
    )

    assert ok["succeeded"] == 1
    assert ok["results"][0]["normalized_variant_key"] == "17-43092919-A-G"
    assert symbolic["failed_records"][0]["error"]["code"] == "UNSUPPORTED_VARIANT_TYPE"
    assert multiallelic["failed_records"][0]["error"]["code"] == "MALFORMED_RECORD"


def test_invalid_position_and_illegal_allele_are_failed_records() -> None:
    invalid_position = rate_variant_batch(
        {"records": [_record(position=0), _record(position="not-a-number")]}
    )
    illegal_allele = rate_variant_batch({"records": [_record(ref="A", alt="N")]})

    assert invalid_position["succeeded"] == 0
    assert invalid_position["failed"] == 2
    assert illegal_allele["failed_records"][0]["error"]["code"] == "variant_normalization"


def test_duplicate_with_formatting_differences_detected_without_merging() -> None:
    result = rate_variant_batch(
        {
            "records": [
                _record(chromosome="chr17", ref="a", alt="g"),
                _record(chromosome="17", ref="A", alt="G"),
            ]
        }
    )

    assert result["succeeded"] == 2
    assert len(result["results"]) == 2
    assert any("Duplicate variant detected" in warning for warning in result["warnings"])


def test_batch_summary_includes_failed_review_conflict_counts() -> None:
    result = rate_variant_batch(
        {
            "records": [
                _record(
                    options={
                        "include_context_consistency": True,
                        "annotations": [
                            {
                                "gene": "TP53",
                                "transcript": "NM_007294.4",
                                "hgvs_c": "NM_007294.4:c.68_69delAG",
                                "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
                                "consequence": "frameshift_variant",
                                "consequence_terms": ["frameshift_variant"],
                                "annotation_source": "test_annotation",
                                "provenance": {
                                    "data_source": "test_annotation",
                                    "raw_record_hash": "abc123",
                                },
                                "raw_fields": {},
                            }
                        ],
                    }
                ),
                _record(variant_type="cnv", alt="<DEL>"),
                _record(),
                _record(),
            ]
        }
    )

    summary = result["summary"]
    assert summary["total_records"] == 4
    assert summary["succeeded"] == 3
    assert summary["failed"] == 1
    assert summary["review_required_count"] == 4
    assert summary["conflict_count"] == 1
    assert summary["failed_records_summary"][0]["code"] == "UNSUPPORTED_VARIANT_TYPE"
    assert summary["duplicate_warnings"]
    assert sum(summary["classification_distribution"].values()) == 3
