from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from variant_pathogenicity_rater.config.thresholds import ComputationalEvidenceThresholds
from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.schemas.evidence import ComputationalPrediction, EvidenceSource
from variant_pathogenicity_rater.schemas.variant import Variant


class PredictionDirection(StrEnum):
    PATHOGENIC = "pathogenic"
    BENIGN = "benign"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class PredictorCall:
    method: str
    direction: PredictionDirection
    reason: str
    score: float | None = None
    transcript: str | None = None
    splice_related: bool = False


class PredictorInterpreter:
    """Abstract predictor interpreter interface."""

    method_names: frozenset[str]

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        raise NotImplementedError

    def matches(self, method: str) -> bool:
        return _normalize_method(method) in self.method_names


def _normalize_method(method: str) -> str:
    return method.strip().lower().replace("_", "").replace("-", "").replace(" ", "")


def _prediction_text(prediction: ComputationalPrediction) -> str:
    return prediction.prediction.strip().lower().replace("_", " ").replace("-", " ")


def _is_benign_prediction_text(text: str) -> bool:
    return any(
        token in text
        for token in ("benign", "tolerated", "no impact", "no splice", "no predicted splice")
    )


def _is_pathogenic_prediction_text(text: str) -> bool:
    return any(
        token in text
        for token in ("deleterious", "damaging", "splice altering", "loss", "gain")
    )


def _score_direction(
    *,
    method: str,
    score: float | None,
    pathogenic_cutoff: float,
    benign_cutoff: float,
    high_is_pathogenic: bool = True,
) -> PredictorCall:
    if score is None:
        return PredictorCall(method=method, direction=PredictionDirection.NEUTRAL, reason="No score.")

    if high_is_pathogenic:
        if score >= pathogenic_cutoff:
            return PredictorCall(
                method=method,
                direction=PredictionDirection.PATHOGENIC,
                reason=f"Score {score:g} meets pathogenic cutoff {pathogenic_cutoff:g}.",
                score=score,
            )
        if score <= benign_cutoff:
            return PredictorCall(
                method=method,
                direction=PredictionDirection.BENIGN,
                reason=f"Score {score:g} meets benign cutoff {benign_cutoff:g}.",
                score=score,
            )
    else:
        if score <= pathogenic_cutoff:
            return PredictorCall(
                method=method,
                direction=PredictionDirection.PATHOGENIC,
                reason=f"Score {score:g} meets pathogenic cutoff {pathogenic_cutoff:g}.",
                score=score,
            )
        if score > benign_cutoff:
            return PredictorCall(
                method=method,
                direction=PredictionDirection.BENIGN,
                reason=f"Score {score:g} meets benign cutoff > {benign_cutoff:g}.",
                score=score,
            )

    return PredictorCall(
        method=method,
        direction=PredictionDirection.NEUTRAL,
        reason=f"Score {score:g} is between configured cutoffs.",
        score=score,
    )


class RevelInterpreter(PredictorInterpreter):
    method_names = frozenset({"revel"})

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        return _score_direction(
            method="REVEL",
            score=prediction.score,
            pathogenic_cutoff=thresholds.revel_pathogenic,
            benign_cutoff=thresholds.revel_benign,
        )


class CaddInterpreter(PredictorInterpreter):
    method_names = frozenset({"cadd"})

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        return _score_direction(
            method="CADD",
            score=prediction.score,
            pathogenic_cutoff=thresholds.cadd_pathogenic,
            benign_cutoff=thresholds.cadd_benign,
        )


class SiftInterpreter(PredictorInterpreter):
    method_names = frozenset({"sift"})

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        text = _prediction_text(prediction)
        if "deleterious" in text or text == "damaging":
            return PredictorCall(
                method="SIFT",
                direction=PredictionDirection.PATHOGENIC,
                reason=f"Prediction label is {prediction.prediction!r}.",
                score=prediction.score,
            )
        if "tolerated" in text or "benign" in text:
            return PredictorCall(
                method="SIFT",
                direction=PredictionDirection.BENIGN,
                reason=f"Prediction label is {prediction.prediction!r}.",
                score=prediction.score,
            )
        return _score_direction(
            method="SIFT",
            score=prediction.score,
            pathogenic_cutoff=thresholds.sift_pathogenic,
            benign_cutoff=thresholds.sift_benign,
            high_is_pathogenic=False,
        )


class PolyPhen2Interpreter(PredictorInterpreter):
    method_names = frozenset({"polyphen2", "polyphen"})

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        text = _prediction_text(prediction)
        if "probably damaging" in text or "possibly damaging" in text or text == "damaging":
            return PredictorCall(
                method="PolyPhen-2",
                direction=PredictionDirection.PATHOGENIC,
                reason=f"Prediction label is {prediction.prediction!r}.",
                score=prediction.score,
            )
        if "benign" in text:
            return PredictorCall(
                method="PolyPhen-2",
                direction=PredictionDirection.BENIGN,
                reason=f"Prediction label is {prediction.prediction!r}.",
                score=prediction.score,
            )
        return _score_direction(
            method="PolyPhen-2",
            score=prediction.score,
            pathogenic_cutoff=thresholds.polyphen2_pathogenic,
            benign_cutoff=thresholds.polyphen2_benign,
        )


class MutationTasterInterpreter(PredictorInterpreter):
    method_names = frozenset({"mutationtaster"})

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        text = _prediction_text(prediction)
        if "disease causing" in text or "deleterious" in text or "damaging" in text:
            return PredictorCall(
                method="MutationTaster",
                direction=PredictionDirection.PATHOGENIC,
                reason=f"Prediction label is {prediction.prediction!r}.",
                score=prediction.score,
            )
        if "polymorphism" in text or "benign" in text:
            return PredictorCall(
                method="MutationTaster",
                direction=PredictionDirection.BENIGN,
                reason=f"Prediction label is {prediction.prediction!r}.",
                score=prediction.score,
            )
        return PredictorCall(
            method="MutationTaster",
            direction=PredictionDirection.NEUTRAL,
            reason=f"Prediction label {prediction.prediction!r} is not mapped.",
            score=prediction.score,
        )


class SpliceAiInterpreter(PredictorInterpreter):
    method_names = frozenset({"spliceai", "spliceaideltascore", "spliceaidelta"})

    def interpret(
        self,
        prediction: ComputationalPrediction,
        thresholds: ComputationalEvidenceThresholds,
    ) -> PredictorCall:
        if prediction.candidate_only:
            reason = "SpliceAI record is candidate-only"
            if prediction.limitations:
                reason = f"{reason}: {'; '.join(prediction.limitations)}"
            return PredictorCall(
                method="SpliceAI",
                direction=PredictionDirection.NEUTRAL,
                reason=reason,
                score=prediction.score,
                transcript=prediction.transcript,
                splice_related=True,
            )
        text = _prediction_text(prediction)
        if (
            prediction.score is not None
            and prediction.score >= thresholds.spliceai_pathogenic
            and _is_benign_prediction_text(text)
        ) or (
            prediction.score is not None
            and prediction.score <= thresholds.spliceai_benign
            and _is_pathogenic_prediction_text(text)
        ):
            return PredictorCall(
                method="SpliceAI",
                direction=PredictionDirection.NEUTRAL,
                reason=(
                    "SpliceAI score and predicted consequence conflict; PP3/BP4 require review."
                ),
                score=prediction.score,
                transcript=prediction.transcript,
                splice_related=True,
            )
        call = _score_direction(
            method="SpliceAI",
            score=prediction.score,
            pathogenic_cutoff=thresholds.spliceai_pathogenic,
            benign_cutoff=thresholds.spliceai_benign,
        )
        return PredictorCall(
            method=call.method,
            direction=call.direction,
            reason=call.reason,
            score=call.score,
            transcript=prediction.transcript,
            splice_related=True,
        )


DEFAULT_INTERPRETERS: tuple[PredictorInterpreter, ...] = (
    RevelInterpreter(),
    CaddInterpreter(),
    SiftInterpreter(),
    PolyPhen2Interpreter(),
    MutationTasterInterpreter(),
    SpliceAiInterpreter(),
)


class ComputationalPredictionProvider(ABC):
    @abstractmethod
    def query(self, variant: Variant) -> list[ComputationalPrediction]:
        raise NotImplementedError


class MockComputationalPredictionProvider(ComputationalPredictionProvider):
    """Offline deterministic provider for mock computational predictor records."""

    def __init__(self, fixtures: dict[str, list[ComputationalPrediction]] | None = None) -> None:
        self.fixtures = fixtures or {}

    def query(self, variant: Variant) -> list[ComputationalPrediction]:
        if variant.variant_id in self.fixtures:
            return self.fixtures[variant.variant_id]

        query = {
            "variant_id": variant.variant_id,
            "genome_build": variant.genome_build,
            "chrom": variant.chrom,
            "pos": variant.pos,
            "ref": variant.ref,
            "alt": variant.alt,
        }
        source = EvidenceSource(
            name="mock_computational_predictions",
            version="offline-fixture-v1",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            query=query,
        )
        provenance = provenance_from_raw_record(
            data_source=source.name,
            source_version=source.version,
            query=query,
            raw_record={"query": query, "provider": source.name},
            parser_version="computational-parser-v1",
            confidence=0.5,
            limitations=[
                "Offline mock computational provider only; no SpliceAI or dbNSFP lookup was performed."
            ],
        )
        attach_provenance_to_source(source, provenance)
        if variant.hgvs_p and ("fs" in variant.hgvs_p.lower() or "ter" in variant.hgvs_p.lower()):
            return [
                ComputationalPrediction(
                    source=source,
                    method="CADD",
                    score=35.0,
                    prediction="deleterious",
                ),
                ComputationalPrediction(
                    source=source,
                    method="MutationTaster",
                    score=0.98,
                    prediction="disease_causing",
                ),
            ]
        return [
            ComputationalPrediction(
                source=source,
                method="REVEL",
                score=0.5,
                prediction="uncertain",
            ),
            ComputationalPrediction(
                source=source,
                method="CADD",
                score=12.0,
                prediction="uncertain",
            ),
        ]


def interpret_prediction(
    prediction: ComputationalPrediction,
    thresholds: ComputationalEvidenceThresholds,
    interpreters: tuple[PredictorInterpreter, ...] = DEFAULT_INTERPRETERS,
) -> PredictorCall:
    for interpreter in interpreters:
        if interpreter.matches(prediction.method):
            call = interpreter.interpret(prediction, thresholds)
            return PredictorCall(
                method=call.method,
                direction=call.direction,
                reason=call.reason,
                score=call.score,
                transcript=prediction.transcript,
                splice_related=call.splice_related,
            )
    return PredictorCall(
        method=prediction.method,
        direction=PredictionDirection.NEUTRAL,
        reason="Unsupported computational predictor method.",
        score=prediction.score,
        transcript=prediction.transcript,
    )
