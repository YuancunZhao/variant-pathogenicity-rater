from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from variant_pathogenicity_rater.schemas.evidence import ComputationalPrediction, EvidenceSource


SUPPORTED_LOCAL_FIELDS = {
    "gene",
    "transcript",
    "hgvs_p",
    "protein_change",
    "revel_score",
    "cadd_score",
    "sift_prediction",
    "polyphen_prediction",
    "mutationtaster_prediction",
    "alphamissense_score",
    "alphamissense_class",
    "spliceai_delta_score",
    "source_version",
    "genome_build",
    "provenance",
}


def parse_local_computational_record(raw: dict[str, Any], *, source_name: str = "local_computational") -> list[ComputationalPrediction]:
    source_version = _text(raw.get("source_version"))
    base_source = {
        "name": source_name,
        "version": source_version,
        "query": {
            "gene": raw.get("gene"),
            "transcript": raw.get("transcript"),
            "hgvs_p": raw.get("hgvs_p"),
            "protein_change": raw.get("protein_change"),
        },
        "provenance": raw.get("provenance"),
    }
    predictions: list[ComputationalPrediction] = []
    _append_score(predictions, raw, base_source, "REVEL", "revel_score")
    _append_score(predictions, raw, base_source, "CADD", "cadd_score")
    _append_label(predictions, raw, base_source, "SIFT", "sift_prediction")
    _append_label(predictions, raw, base_source, "PolyPhen", "polyphen_prediction")
    _append_label(predictions, raw, base_source, "MutationTaster", "mutationtaster_prediction")
    if raw.get("alphamissense_score") not in (None, "") or raw.get("alphamissense_class"):
        predictions.append(
            _prediction(
                raw,
                base_source,
                "AlphaMissense",
                _float(raw.get("alphamissense_score")),
                _text(raw.get("alphamissense_class")) or "uncertain",
            )
        )
    if raw.get("spliceai_delta_score") not in (None, ""):
        predictions.append(
            _prediction(
                raw,
                base_source,
                "SpliceAI",
                _float(raw.get("spliceai_delta_score")),
                _text(raw.get("spliceai_prediction")) or "splice delta score",
            )
        )
    return predictions


def load_local_computational_file(path: str | Path, *, source_name: str = "local_computational") -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".tsv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("records", [payload])
    return [record for record in payload if isinstance(record, dict)]


class OnlineComputationalPredictionProviderPlaceholder:
    """Disabled-by-default placeholder for future online predictors with cache/provenance."""

    def query(self, *_args: Any, **_kwargs: Any) -> list[ComputationalPrediction]:
        raise RuntimeError(
            "Online computational prediction provider is disabled by default; "
            "failures must be reported as limitations rather than interpreted evidence."
        )


def _append_score(
    predictions: list[ComputationalPrediction],
    raw: dict[str, Any],
    source: dict[str, Any],
    method: str,
    field: str,
) -> None:
    if raw.get(field) not in (None, ""):
        predictions.append(_prediction(raw, source, method, _float(raw.get(field)), "score"))


def _append_label(
    predictions: list[ComputationalPrediction],
    raw: dict[str, Any],
    source: dict[str, Any],
    method: str,
    field: str,
) -> None:
    if raw.get(field):
        predictions.append(_prediction(raw, source, method, None, _text(raw.get(field)) or "uncertain"))


def _prediction(
    raw: dict[str, Any],
    source: dict[str, Any],
    method: str,
    score: float | None,
    prediction: str,
) -> ComputationalPrediction:
    return ComputationalPrediction(
        source=EvidenceSource.model_validate(source),
        method=method,
        score=score,
        prediction=prediction,
        transcript=_text(raw.get("transcript")),
        hgvs_p=_text(raw.get("hgvs_p")),
        protein_change=_text(raw.get("protein_change")),
        genome_build=_text(raw.get("genome_build")),
        limitations=[],
    )


def _text(value: Any) -> str | None:
    return str(value).strip() if value not in (None, "") else None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
