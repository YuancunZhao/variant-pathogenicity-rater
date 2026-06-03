from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient
from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
)
from variant_pathogenicity_rater.evidence.computational import ComputationalPredictionProvider
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceSource,
    SplicePrediction,
)
from variant_pathogenicity_rater.schemas.variant import Variant


ENSEMBL_VEP_ENDPOINT = "https://rest.ensembl.org/vep/homo_sapiens/region"
SUPPORTED_PREDICTORS = {
    "CADD": ("cadd_phred", "cadd_raw"),
    "REVEL": ("revel_score",),
    "SIFT": ("sift_score", "sift_prediction"),
    "PolyPhen": ("polyphen_score", "polyphen_prediction"),
    "MutationTaster": ("mutationtaster_score", "mutationtaster_prediction"),
    "AlphaMissense": ("alphamissense_score", "alphamissense_prediction"),
}


class EnsemblVEPOnlineProvider(ComputationalPredictionProvider):
    def __init__(
        self,
        config: DataSourceConfig,
        *,
        http_client: Any | None = None,
    ) -> None:
        if not config.online_enabled:
            raise RuntimeError("Ensembl VEP online mode requires explicit online_enabled=true.")
        self.config = config
        self.cache = DiskCache(config.cache_dir or ".cache/variant_pathogenicity_rater/vep")
        self.http_client = http_client or ProviderHTTPClient(config)

    def query(self, variant: Variant) -> list[ComputationalPrediction]:
        query = _variant_query(variant)
        try:
            entry, cache_hit = self.cache.get_or_set(
                provider=self.config.name,
                mode=str(self.config.mode),
                source_version=self._source_version(),
                query=query,
                loader=lambda: self._load_payload(query),
                ttl_seconds=self.config.ttl_seconds,
            )
            return parse_vep_payload(
                entry.payload,
                variant,
                query=query,
                config=self.config,
                source_version=self._source_version(),
                cache_hit=cache_hit,
            )
        except Exception as exc:  # noqa: BLE001 - provider failure must degrade.
            source = _source(
                config=self.config,
                source_version=self._source_version(),
                query=query,
                raw_payload={"query": query, "error": f"{exc.__class__.__name__}: {exc}"},
                cache_hit=False,
                limitations=[
                    f"Ensembl VEP online query failed: {exc.__class__.__name__}: {exc}",
                    "VEP online failure was captured as a limitation; interpretation continued.",
                ],
            )
            return [
                ComputationalPrediction(
                    source=source,
                    method="EnsemblVEP",
                    prediction="unavailable",
                    genome_build=str(variant.genome_build),
                    candidate_only=True,
                    limitations=[
                        f"Ensembl VEP online query failed: {exc.__class__.__name__}: {exc}",
                        "No PP3/BP4 evidence is generated directly by VEP provider failure.",
                    ],
                )
            ]

    def _load_payload(self, query: dict[str, Any]) -> dict[str, Any]:
        params = {
            "CADD": "1",
            "SpliceAI": "1",
            "AlphaMissense": "1",
        }
        region = f"{query['chrom']}:{query['pos']}-{query['pos']}:1/{query['ref']}/{query['alt']}"
        payload = self.http_client.get_json(f"{ENSEMBL_VEP_ENDPOINT}/{region}", params=params)
        return {
            "provider": "EnsemblVEPOnlineProvider",
            "source_version": self._source_version(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": ENSEMBL_VEP_ENDPOINT,
            "query": query,
            "payload": payload,
        }

    def _source_version(self) -> str:
        return self.config.source_version or "Ensembl REST VEP live"


def parse_vep_payload(
    payload: dict[str, Any],
    variant: Variant,
    *,
    query: dict[str, Any],
    config: DataSourceConfig,
    source_version: str,
    cache_hit: bool,
) -> list[ComputationalPrediction]:
    records = payload.get("payload")
    if not isinstance(records, list):
        records = []
    predictions: list[ComputationalPrediction] = []
    limitations: list[str] = [
        "Ensembl VEP online source supplies computational and consequence facts only; PP3/BP4 require existing evaluator gates.",
    ]
    for record in records:
        if not isinstance(record, dict):
            continue
        transcript_consequences = [
            item for item in record.get("transcript_consequences") or [] if isinstance(item, dict)
        ]
        if not transcript_consequences:
            limitations.append("VEP response did not include transcript consequences.")
        for consequence in transcript_consequences or [{}]:
            consequence_limitations = [
                *limitations,
                *_missing_predictor_limitations(consequence),
            ]
            source = _source(
                config=config,
                source_version=source_version,
                query=query,
                raw_payload={"record": record, "transcript_consequence": consequence},
                cache_hit=cache_hit,
                limitations=consequence_limitations,
            )
            for prediction in _predictors_from_consequence(
                consequence,
                source,
                variant,
                consequence_limitations,
            ):
                predictions.append(prediction)
            splice = _spliceai_prediction(consequence, source, variant)
            if splice is not None:
                predictions.append(splice)
            if not predictions:
                predictions.append(
                    ComputationalPrediction(
                        source=source,
                        method="EnsemblVEP",
                        prediction=str(
                            consequence.get("consequence_terms")
                            or record.get("most_severe_consequence")
                            or "consequence_available"
                        ),
                        transcript=consequence.get("transcript_id"),
                        hgvs_p=consequence.get("hgvsp"),
                        protein_change=consequence.get("hgvsp"),
                        genome_build=str(variant.genome_build),
                        candidate_only=True,
                        limitations=[
                            *consequence_limitations,
                            "No supported calibrated predictor score was present in this VEP response.",
                        ],
                    )
                )
    if not predictions:
        source = _source(
            config=config,
            source_version=source_version,
            query=query,
            raw_payload=payload,
            cache_hit=cache_hit,
            limitations=[*limitations, "No usable Ensembl VEP records were parsed."],
        )
        predictions.append(
            ComputationalPrediction(
                source=source,
                method="EnsemblVEP",
                prediction="unavailable",
                genome_build=str(variant.genome_build),
                candidate_only=True,
                limitations=[*limitations, "No usable Ensembl VEP records were parsed."],
            )
        )
    return predictions


def _predictors_from_consequence(
    consequence: dict[str, Any],
    source: EvidenceSource,
    variant: Variant,
    limitations: list[str],
) -> list[ComputationalPrediction]:
    predictions: list[ComputationalPrediction] = []
    for method, keys in SUPPORTED_PREDICTORS.items():
        score = _first_float(*(consequence.get(key) for key in keys))
        label = _first_text(
            *(consequence.get(key) for key in keys if "prediction" in key or "pred" in key)
        )
        if score is None and label is None:
            continue
        predictions.append(
            ComputationalPrediction(
                source=source,
                method=method,
                score=score,
                prediction=label or _prediction_from_score(method, score),
                transcript=consequence.get("transcript_id"),
                hgvs_p=consequence.get("hgvsp"),
                protein_change=consequence.get("hgvsp"),
                genome_build=str(variant.genome_build),
                candidate_only=False,
                limitations=limitations,
            )
        )
    return predictions


def _missing_predictor_limitations(consequence: dict[str, Any]) -> list[str]:
    missing = []
    for method, keys in SUPPORTED_PREDICTORS.items():
        if all(consequence.get(key) is None for key in keys):
            missing.append(method)
    if not missing:
        return []
    return [
        "VEP response did not include supported predictor field(s): "
        f"{', '.join(missing)}."
    ]


def _spliceai_prediction(
    consequence: dict[str, Any],
    source: EvidenceSource,
    variant: Variant,
) -> ComputationalPrediction | None:
    splice_payload = consequence.get("spliceai") or consequence.get("SpliceAI")
    if not isinstance(splice_payload, dict):
        return None
    scores = {
        "DS_AG": _first_float(splice_payload.get("DS_AG"), splice_payload.get("ds_ag")),
        "DS_AL": _first_float(splice_payload.get("DS_AL"), splice_payload.get("ds_al")),
        "DS_DG": _first_float(splice_payload.get("DS_DG"), splice_payload.get("ds_dg")),
        "DS_DL": _first_float(splice_payload.get("DS_DL"), splice_payload.get("ds_dl")),
    }
    max_score = max((value or 0.0) for value in scores.values())
    if max_score <= 0:
        return None
    splice = SplicePrediction(
        source=source,
        **scores,
        max_delta_score=max_score,
        predicted_consequence=str(splice_payload.get("predicted_consequence") or "splice_effect"),
        affected_gene=str(splice_payload.get("gene") or variant.gene_symbol or "unknown"),
        transcript=consequence.get("transcript_id"),
        source_version=source.version,
        genome_build=str(variant.genome_build),
        candidate_only=False,
        limitations=[
            "SpliceAI is computational prediction only; it is not RNA validation or functional evidence.",
        ],
    )
    return ComputationalPrediction(
        source=source,
        method="SpliceAI",
        score=max_score,
        prediction=splice.predicted_consequence,
        transcript=consequence.get("transcript_id"),
        hgvs_p=consequence.get("hgvsp"),
        protein_change=consequence.get("hgvsp"),
        genome_build=str(variant.genome_build),
        splice_prediction=splice,
        limitations=splice.limitations,
    )


def _source(
    *,
    config: DataSourceConfig,
    source_version: str,
    query: dict[str, Any],
    raw_payload: dict[str, Any],
    cache_hit: bool | None,
    limitations: list[str],
) -> EvidenceSource:
    source = EvidenceSource(
        name=config.name,
        version=source_version,
        url="https://rest.ensembl.org/",
        retrieval_timestamp=raw_payload.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
        query=query,
    )
    provenance = provenance_from_raw_record(
        data_source=config.name,
        source_version=source_version,
        query=query,
        raw_record=raw_payload,
        parser_version=config.parser_version,
        confidence=0.5,
        source_url="https://rest.ensembl.org/",
        endpoint=raw_payload.get("endpoint") or ENSEMBL_VEP_ENDPOINT,
        provider_mode=str(config.mode),
        cache_hit=cache_hit,
        request_method="GET",
        request_url=ENSEMBL_VEP_ENDPOINT,
        raw_payload_kind="rest_json",
        limitations=limitations,
    )
    attach_provenance_to_source(source, provenance)
    return source


def _variant_query(variant: Variant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "genome_build": variant.genome_build,
        "chrom": variant.chrom,
        "pos": variant.pos,
        "ref": variant.ref,
        "alt": variant.alt,
        "gene": variant.gene_symbol,
        "hgvs_c": variant.hgvs_c,
        "hgvs_p": variant.hgvs_p,
    }


def _first_float(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.split()[0])
            except ValueError:
                continue
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _prediction_from_score(method: str, score: float | None) -> str:
    if score is None:
        return "unknown"
    if method == "CADD":
        return "deleterious" if score >= 20 else "not_deleterious"
    if method in {"REVEL", "AlphaMissense"}:
        return "deleterious" if score >= 0.5 else "benign_or_uncertain"
    return "score_available"
