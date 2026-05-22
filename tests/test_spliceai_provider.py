from __future__ import annotations

import json

from variant_pathogenicity_rater.acmg.computational_rules import (
    evaluate_computational_predictions,
)
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.providers import build_computational_provider
from variant_pathogenicity_rater.schemas import ComputationalPrediction, EvidenceSource, Transcript, Variant


def _variant(**overrides: object) -> Variant:
    payload = {
        "variant_id": "GRCh38-1-12345-A-G",
        "genome_build": "GRCh38",
        "variant_type": "snv",
        "chrom": "1",
        "pos": 12345,
        "ref": "A",
        "alt": "G",
        "gene_symbol": "GENE1",
        "transcript": {
            "accession": "NM_000001",
            "version": "1",
            "gene_symbol": "GENE1",
            "consequence": "missense_variant",
        },
    }
    payload.update(overrides)
    return Variant.model_validate(payload)


def _provider(tmp_path, records: list[dict[str, object]], suffix: str = ".jsonl"):
    path = tmp_path / f"spliceai{suffix}"
    if suffix == ".tsv":
        headers = list(records[0])
        lines = ["\t".join(headers)]
        lines.extend("\t".join(str(record.get(header, "")) for header in headers) for record in records)
        path.write_text("\n".join(lines), encoding="utf-8")
    else:
        path.write_text(
            "\n".join(json.dumps(record) for record in records),
            encoding="utf-8",
        )
    return build_computational_provider(
        DataSourceConfig(
            name="spliceai",
            mode="local_file",
            enabled=True,
            source_version="spliceai-local-v1",
            parser_version="spliceai-local-parser-test",
            cache_dir=str(tmp_path / "cache"),
            local_file=str(path),
        )
    )


def _splice_record(**overrides: object) -> dict[str, object]:
    record = {
        "chrom": "1",
        "pos": 12345,
        "ref": "A",
        "alt": "G",
        "genome_build": "GRCh38",
        "DS_AG": 0.82,
        "DS_AL": 0.01,
        "DS_DG": 0.02,
        "DS_DL": 0.03,
        "max_delta_score": 0.82,
        "predicted_consequence": "splice altering",
        "affected_gene": "GENE1",
        "transcript": "NM_000001.1",
        "source_version": "SpliceAI-1.3.1-local",
    }
    record.update(overrides)
    return record


def test_spliceai_local_file_hit_jsonl_by_coordinate(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record()]).query(_variant())

    assert len(predictions) == 1
    prediction = predictions[0]
    assert prediction.method == "SpliceAI"
    assert prediction.score == 0.82
    assert prediction.splice_prediction is not None
    assert prediction.splice_prediction.DS_AG == 0.82
    assert prediction.splice_prediction.affected_gene == "GENE1"
    assert prediction.source.provenance.data_source == "spliceai"


def test_spliceai_local_file_hit_tsv_by_coordinate(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record()], suffix=".tsv").query(_variant())

    assert len(predictions) == 1
    assert predictions[0].splice_prediction is not None
    assert predictions[0].splice_prediction.source_version == "SpliceAI-1.3.1-local"


def test_spliceai_local_file_miss_returns_no_predictions(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record(pos=99999)]).query(_variant())

    assert predictions == []
    evidence_items, review_flags, _ = evaluate_computational_predictions(_variant(), predictions)
    assert evidence_items == []
    assert review_flags == []


def test_high_spliceai_delta_can_only_apply_pp3_supporting(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record()]).query(_variant())

    evidence_items, _, _ = evaluate_computational_predictions(
        _variant(),
        predictions,
        ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=1),
    )

    assert [item.code for item in evidence_items] == ["PP3"]
    assert evidence_items[0].strength == "supporting"
    assert not {"PVS1", "PS3"}.intersection({item.code for item in evidence_items})
    assert "does not replace PVS1 or PS3" in evidence_items[0].reason


def test_low_spliceai_delta_with_benign_consensus_can_apply_bp4_supporting(tmp_path) -> None:
    predictions = _provider(
        tmp_path,
        [
            _splice_record(
                DS_AG=0.01,
                DS_AL=0.02,
                DS_DG=0.01,
                DS_DL=0.03,
                max_delta_score=0.03,
                predicted_consequence="no predicted splice impact",
            )
        ],
    ).query(_variant())
    predictions.append(
        ComputationalPrediction(
            source=EvidenceSource(name="local_REVEL"),
            method="REVEL",
            score=0.02,
            prediction="benign",
        )
    )

    evidence_items, review_flags, summary = evaluate_computational_predictions(_variant(), predictions)

    assert review_flags == []
    assert [item.code for item in evidence_items] == ["BP4"]
    assert evidence_items[0].strength == "supporting"
    assert summary["benign_support_count"] == 2


def test_transcript_mismatch_is_candidate_only(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record(transcript="NM_999999.1")]).query(_variant())

    assert predictions[0].candidate_only is True
    evidence_items, review_flags, summary = evaluate_computational_predictions(
        _variant(),
        predictions,
        ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=1),
    )
    assert evidence_items == []
    assert review_flags[0].code == "COMPUTATIONAL_PREDICTION_INSUFFICIENT"
    assert summary["pathogenic_support_count"] == 0


def test_genome_build_mismatch_is_candidate_only_limitation(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record(genome_build="GRCh37")]).query(_variant())

    assert predictions[0].candidate_only is True
    assert any("genome build differs" in limitation for limitation in predictions[0].limitations)
    evidence_items, _, _ = evaluate_computational_predictions(
        _variant(),
        predictions,
        ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=1),
    )
    assert evidence_items == []


def test_conflicting_splice_prediction_sets_review_flag(tmp_path) -> None:
    predictions = _provider(
        tmp_path,
        [_splice_record(max_delta_score=0.91, predicted_consequence="no predicted splice impact")],
    ).query(_variant())

    evidence_items, review_flags, _ = evaluate_computational_predictions(
        _variant(),
        predictions,
        ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=1),
    )

    assert evidence_items == []
    assert review_flags[0].code == "SPLICEAI_PREDICTION_CONFLICT"


def test_spliceai_does_not_directly_upgrade_pvs1_or_functional_evidence(tmp_path) -> None:
    predictions = _provider(tmp_path, [_splice_record()]).query(
        _variant(
            transcript=Transcript(
                accession="NM_000001",
                version="1",
                gene_symbol="GENE1",
                consequence="splice_donor_variant",
                canonical=True,
            )
        )
    )

    evidence_items, _, _ = evaluate_computational_predictions(
        _variant(),
        predictions,
        ComputationalEvidenceThresholds(min_pathogenic_supporting_tools=1),
    )

    assert {item.code for item in evidence_items} <= {"PP3"}
