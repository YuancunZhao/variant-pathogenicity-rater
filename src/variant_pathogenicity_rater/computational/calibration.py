from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.computational.schema import (
    PredictorCall,
    PredictorDirection,
    PredictorGroup,
)
from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.schemas.evidence import ComputationalPrediction


MISSENSE_METHODS = {
    "revel": "REVEL",
    "cadd": "CADD",
    "sift": "SIFT",
    "polyphen": "PolyPhen",
    "polyphen2": "PolyPhen",
    "mutationtaster": "MutationTaster",
    "alphamissense": "AlphaMissense",
}

SPLICE_METHODS = {
    "spliceai": "SpliceAI",
    "spliceaideltascore": "SpliceAI",
    "spliceaidelta": "SpliceAI",
    "dbscsnv": "dbscSNV",
}


def calibrate_prediction(
    prediction: ComputationalPrediction,
    thresholds: ComputationalEvidenceThresholds,
) -> PredictorCall:
    method_key = normalize_method(prediction.method)
    if method_key in MISSENSE_METHODS:
        return _calibrate_missense(prediction, thresholds, MISSENSE_METHODS[method_key])
    if method_key in SPLICE_METHODS:
        return _calibrate_splice(prediction, thresholds, SPLICE_METHODS[method_key])
    return PredictorCall(
        method=prediction.method,
        group=PredictorGroup.UNKNOWN,
        direction=PredictorDirection.AMBIGUOUS,
        score=prediction.score,
        prediction=prediction.prediction,
        threshold=prediction.threshold,
        transcript=prediction.transcript,
        protein_change=prediction.protein_change,
        hgvs_p=prediction.hgvs_p,
        source_name=prediction.source.name,
        source_version=prediction.source.version,
        genome_build=prediction.genome_build,
        calibrated=False,
        candidate_only=True,
        reason="Unsupported computational predictor method.",
        limitations=[*prediction.limitations, "Unsupported predictor placeholder; not used for applied PP3/BP4."],
        provenance=prediction.source.provenance,
    )


def normalize_method(method: str) -> str:
    return method.strip().lower().replace("_", "").replace("-", "").replace(" ", "")


def _text(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", " ").replace("-", " ")


def _calibrate_missense(
    prediction: ComputationalPrediction,
    thresholds: ComputationalEvidenceThresholds,
    method: str,
) -> PredictorCall:
    text = _text(prediction.prediction)
    direction = PredictorDirection.AMBIGUOUS
    reason = f"Prediction label {prediction.prediction!r} is ambiguous."
    score = prediction.score
    threshold: float | None = prediction.threshold

    if method == "REVEL":
        direction, reason, threshold = _high_score_direction(score, thresholds.revel_pathogenic, thresholds.revel_benign)
    elif method == "CADD":
        direction, reason, threshold = _high_score_direction(score, thresholds.cadd_pathogenic, thresholds.cadd_benign)
    elif method == "SIFT":
        if "deleterious" in text or text == "damaging":
            direction, reason = PredictorDirection.PATHOGENIC, f"Prediction label is {prediction.prediction!r}."
        elif "tolerated" in text or "benign" in text:
            direction, reason = PredictorDirection.BENIGN, f"Prediction label is {prediction.prediction!r}."
        else:
            direction, reason, threshold = _low_score_direction(score, thresholds.sift_pathogenic, thresholds.sift_benign)
    elif method == "PolyPhen":
        if "probably damaging" in text or "possibly damaging" in text or text == "damaging":
            direction, reason = PredictorDirection.PATHOGENIC, f"Prediction label is {prediction.prediction!r}."
        elif "benign" in text:
            direction, reason = PredictorDirection.BENIGN, f"Prediction label is {prediction.prediction!r}."
        else:
            direction, reason, threshold = _high_score_direction(score, thresholds.polyphen2_pathogenic, thresholds.polyphen2_benign)
    elif method == "MutationTaster":
        if "disease causing" in text or "deleterious" in text or "damaging" in text:
            direction, reason = PredictorDirection.PATHOGENIC, f"Prediction label is {prediction.prediction!r}."
        elif "polymorphism" in text or "benign" in text:
            direction, reason = PredictorDirection.BENIGN, f"Prediction label is {prediction.prediction!r}."
    elif method == "AlphaMissense":
        if "likely pathogenic" in text or "pathogenic" in text:
            direction, reason = PredictorDirection.PATHOGENIC, f"Prediction label is {prediction.prediction!r}."
        elif "likely benign" in text or "benign" in text:
            direction, reason = PredictorDirection.BENIGN, f"Prediction label is {prediction.prediction!r}."
        elif score is not None:
            direction, reason, threshold = _high_score_direction(score, 0.564, 0.34)

    return _call(prediction, method, PredictorGroup.MISSENSE, direction, reason, threshold)


def _calibrate_splice(
    prediction: ComputationalPrediction,
    thresholds: ComputationalEvidenceThresholds,
    method: str,
) -> PredictorCall:
    text = _text(prediction.prediction)
    if method == "dbscSNV":
        return _call(
            prediction,
            method,
            PredictorGroup.SPLICE,
            PredictorDirection.AMBIGUOUS,
            "dbscSNV is a placeholder predictor in this phase.",
            prediction.threshold,
            candidate_only=True,
            extra_limitations=["dbscSNV placeholder; not sufficient for applied evidence."],
        )

    direction, reason, threshold = _high_score_direction(
        prediction.score,
        thresholds.spliceai_pathogenic,
        thresholds.spliceai_benign,
    )
    if direction == PredictorDirection.PATHOGENIC and ("benign" in text or "no predicted splice" in text):
        direction = PredictorDirection.AMBIGUOUS
        reason = "SpliceAI score and label conflict."
    elif direction == PredictorDirection.BENIGN and any(token in text for token in ("splice altering", "loss", "gain")):
        direction = PredictorDirection.AMBIGUOUS
        reason = "SpliceAI low score conflicts with splice-altering label."
    return _call(prediction, method, PredictorGroup.SPLICE, direction, reason, threshold)


def _high_score_direction(
    score: float | None,
    pathogenic_cutoff: float,
    benign_cutoff: float,
) -> tuple[PredictorDirection, str, float | None]:
    if score is None:
        return PredictorDirection.AMBIGUOUS, "No score was supplied.", None
    if score >= pathogenic_cutoff:
        return PredictorDirection.PATHOGENIC, f"Score {score:g} meets pathogenic cutoff {pathogenic_cutoff:g}.", pathogenic_cutoff
    if score <= benign_cutoff:
        return PredictorDirection.BENIGN, f"Score {score:g} meets benign cutoff {benign_cutoff:g}.", benign_cutoff
    return PredictorDirection.NEUTRAL, f"Score {score:g} is between calibrated cutoffs.", None


def _low_score_direction(
    score: float | None,
    pathogenic_cutoff: float,
    benign_cutoff: float,
) -> tuple[PredictorDirection, str, float | None]:
    if score is None:
        return PredictorDirection.AMBIGUOUS, "No score was supplied.", None
    if score <= pathogenic_cutoff:
        return PredictorDirection.PATHOGENIC, f"Score {score:g} meets pathogenic cutoff <= {pathogenic_cutoff:g}.", pathogenic_cutoff
    if score > benign_cutoff:
        return PredictorDirection.BENIGN, f"Score {score:g} meets benign cutoff > {benign_cutoff:g}.", benign_cutoff
    return PredictorDirection.NEUTRAL, f"Score {score:g} is between calibrated cutoffs.", None


def _call(
    prediction: ComputationalPrediction,
    method: str,
    group: PredictorGroup,
    direction: PredictorDirection,
    reason: str,
    threshold: float | None,
    *,
    candidate_only: bool | None = None,
    extra_limitations: list[str] | None = None,
) -> PredictorCall:
    splice = prediction.splice_prediction
    return PredictorCall(
        method=method,
        group=group,
        direction=direction,
        score=prediction.score,
        prediction=prediction.prediction,
        threshold=threshold,
        transcript=prediction.transcript or (splice.transcript if splice else None),
        protein_change=prediction.protein_change,
        hgvs_p=prediction.hgvs_p,
        source_name=prediction.source.name,
        source_version=prediction.source.version,
        genome_build=prediction.genome_build or (splice.genome_build if splice else None),
        calibrated=direction != PredictorDirection.AMBIGUOUS,
        candidate_only=prediction.candidate_only if candidate_only is None else candidate_only,
        reason=reason,
        limitations=[*prediction.limitations, *(splice.limitations if splice else []), *(extra_limitations or [])],
        provenance=prediction.source.provenance,
    )


def call_to_summary(call: PredictorCall) -> dict[str, Any]:
    summary = call.model_dump(mode="json")
    if call.candidate_only:
        summary["direction"] = PredictorDirection.AMBIGUOUS.value
        summary["counted_for_consensus"] = False
    else:
        summary["counted_for_consensus"] = True
    return summary
