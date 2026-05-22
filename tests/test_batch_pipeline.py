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
