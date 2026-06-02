from __future__ import annotations

import json

from variant_pathogenicity_rater.cli import main
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch


def test_cli_help(capsys) -> None:
    exit_code = main(["--help"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "vpr" in captured.out
    assert "annotated-batch" in captured.out


def test_single_rate_json(capsys) -> None:
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
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["mock_mode"] is True
    assert payload["classification_result"]["human_review_required"] is True


def test_single_rate_markdown_shows_pvs1_decision_path(capsys) -> None:
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
            "--output",
            "markdown",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PVS1 decision path" in captured.out
    assert "Candidate / Review-Note Evidence" in captured.out


def test_single_rate_markdown_zh_alias_outputs_chinese_laboratory_report(capsys) -> None:
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
            "--output",
            "markdown-zh",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "# 变异致病性机器辅助判读报告" in captured.out
    assert "## 报告摘要" in captured.out
    assert "不是最终临床结论" in captured.out


def test_single_rate_explicit_chinese_markdown_report_options(capsys) -> None:
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
            "--output",
            "markdown",
            "--language",
            "zh",
            "--report-mode",
            "laboratory",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "## 人工复核清单" in captured.out
    assert "候选/复核证据" in captured.out


def test_batch_jsonl(capsys, tmp_path) -> None:
    input_path = tmp_path / "batch.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(_record()),
                json.dumps(_record(position=43092920, ref="A", alt="G")),
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "batch",
            "--input",
            str(input_path),
            "--format",
            "jsonl",
            "--output-format",
            "jsonl",
        ]
    )

    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]
    assert exit_code == 0
    assert [line["type"] for line in lines] == ["result", "result", "summary"]
    assert lines[-1]["succeeded"] == 2
    assert lines[-1]["failed"] == 0


def test_batch_language_zh_adds_internal_review_summary(capsys, tmp_path) -> None:
    input_path = tmp_path / "batch.jsonl"
    input_path.write_text(json.dumps(_record()), encoding="utf-8")

    base_exit_code = main(
        [
            "batch",
            "--input",
            str(input_path),
            "--format",
            "jsonl",
        ]
    )
    base_payload = json.loads(capsys.readouterr().out)

    exit_code = main(
        [
            "batch",
            "--input",
            str(input_path),
            "--format",
            "jsonl",
            "--language",
            "zh",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert base_exit_code == 0
    assert exit_code == 0
    assert payload["summary_zh"]["人工复核必需"] is True
    assert "不替代单条变异人工复核" in payload["summary_zh"]["用途"]
    assert payload["summary"] == base_payload["summary"]
    assert payload["total_records"] == base_payload["total_records"]
    assert payload["succeeded"] == base_payload["succeeded"]
    assert payload["failed"] == base_payload["failed"]


def test_single_rate_with_clingen_erepo_local_file(capsys, tmp_path) -> None:
    erepo = tmp_path / "erepo.tsv"
    erepo.write_text(
        "record_id\tgene\tca_id\thgvs_c\tdisease_condition\tclassification\tclassification_date\tclassification_version\tsource_url\n"
        "erepo-cli\tBRCA1\tCA000000001\tNM_007294.4:c.68_69delAG\tHereditary breast and ovarian cancer\tPathogenic\t2025-01-15\tv1\thttps://erepo.example/erepo-cli\n",
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

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["clingen_erepo"]["records"][0]["record_id"] == "erepo-cli"
    assert "ClinGen Evidence Repository Match" in payload["report_text"]


def test_noisy_input_cli_batch_and_python_batch_have_consistent_status(capsys, tmp_path) -> None:
    text = (
        "\ufeff# exported by spreadsheet\n"
        "Gene,Transcript,HGVSc,Chromosome,Position,Ref,Alt,Unnamed: 8,Disease\n"
        " brca1 , nm_007294.4 ,NM_007294.4:c.68A>G,chr17,43092919,a,g,,HBOC\n"
        "BAD,,,,,,,\n"
    )
    input_path = tmp_path / "noisy.csv"
    input_path.write_text(text, encoding="utf-8")
    python_result = rate_variant_batch(
        {"input_format": "csv", "input_text": text, "options": {"mock_mode": True}}
    )

    exit_code = main(
        [
            "batch",
            "--input",
            str(input_path),
            "--format",
            "csv",
        ]
    )

    captured = capsys.readouterr()
    cli_result = json.loads(captured.out)
    assert exit_code == 0
    assert [item["status"] for item in cli_result["results"]] == [
        item["status"] for item in python_result["results"]
    ]


def test_annotated_vep_fixture(capsys, tmp_path) -> None:
    input_path = tmp_path / "vep.tsv"
    input_path.write_text(
        """## ENSEMBL VARIANT EFFECT PREDICTOR
#Uploaded_variation\tSYMBOL\tFeature\tHGVSc\tHGVSp\tConsequence\tCANONICAL\tMANE_SELECT\tBIOTYPE
17_43092919_AG/A\tBRCA1\tNM_007294.4\tNM_007294.4:c.68_69delAG\tNP_009225.1:p.Glu23ValfsTer17\tframeshift_variant\tYES\tYES\tprotein_coding
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "annotated-batch",
            "--input",
            str(input_path),
            "--source",
            "vep",
            "--include-report",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["annotation_parse"]["parsed"] == 1
    assert payload["summary"]["succeeded"] == 1
    assert payload["summary"]["failed"] == 0
    assert any("does not directly generate ACMG evidence" in item for item in payload["limitations"])
    assert payload["batch"]["results"][0]["annotation_provenance"]
    result = payload["batch"]["results"][0]
    assert result["normalization_identity"]["normalized_variant_key"] == "17-43092919-AG-A"
    assert result["transcript_selection_summary"]["selected_transcript"] == "NM_007294.4"
    assert result["context_consistency_summary"]["status"] in {
        "ok",
        "warning",
        "conflict",
        "insufficient",
    }
    pvs1 = next(item for item in result["review_note_evidence"] if item["code"] == "PVS1")
    assert pvs1["supporting_data"]["pvs1_decision"]["decision_path"]


def test_output_file_writing(tmp_path, capsys) -> None:
    input_path = tmp_path / "batch.jsonl"
    output_path = tmp_path / "result.json"
    input_path.write_text(json.dumps(_record()), encoding="utf-8")

    exit_code = main(
        [
            "batch",
            "--input",
            str(input_path),
            "--format",
            "jsonl",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert captured.out == ""
    assert payload["succeeded"] == 1


def test_invalid_input_exit_code(capsys, tmp_path) -> None:
    missing = tmp_path / "missing.jsonl"

    exit_code = main(["batch", "--input", str(missing), "--format", "jsonl"])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "cannot read input file" in captured.err


def test_check_env_command(capsys) -> None:
    exit_code = main(["check-env"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Python executable:" in captured.out
    assert "project import status:" in captured.out


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
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
    }
    record.update(overrides)
    return record
