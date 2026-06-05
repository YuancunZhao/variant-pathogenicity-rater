from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.data_sources.config import DataSourceConfig
from variant_pathogenicity_rater.data_sources.http import ProviderHTTPClient
from variant_pathogenicity_rater.data_sources.provenance import (
    attach_provenance_to_source,
    provenance_from_raw_record,
    raw_record_hash,
)
from variant_pathogenicity_rater.evidence.computational import ComputationalPredictionProvider
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceSource,
    SplicePrediction,
)
from variant_pathogenicity_rater.schemas.variant import Variant


ENSEMBL_VEP_ENDPOINT = "https://rest.ensembl.org/vep/homo_sapiens/region"
ENSEMBL_VEP_HGVS_ENDPOINT = "https://rest.ensembl.org/vep/human/hgvs"
SUPPORTED_PREDICTORS = {
    "CADD": ("cadd_phred", "cadd_raw"),
    "REVEL": ("revel_score",),
    "SIFT": ("sift_score", "sift_prediction"),
    "PolyPhen": ("polyphen_score", "polyphen_prediction"),
    "MutationTaster": ("mutationtaster_score", "mutationtaster_prediction"),
    "AlphaMissense": ("alphamissense_score", "alphamissense_prediction"),
}
AA_THREE_LETTER = {
    "A": "Ala",
    "R": "Arg",
    "N": "Asn",
    "D": "Asp",
    "C": "Cys",
    "Q": "Gln",
    "E": "Glu",
    "G": "Gly",
    "H": "His",
    "I": "Ile",
    "L": "Leu",
    "K": "Lys",
    "M": "Met",
    "F": "Phe",
    "P": "Pro",
    "S": "Ser",
    "T": "Thr",
    "W": "Trp",
    "Y": "Tyr",
    "V": "Val",
    "X": "Ter",
    "*": "Ter",
}


class VEPProviderAttemptsError(RuntimeError):
    def __init__(self, message: str, *, attempts: list[dict[str, Any]], query: dict[str, Any]) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.query = query

    def to_payload(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "attempts": self.attempts,
            "query": self.query,
            "cause_type": self.__class__.__name__,
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
            raw_error = _error_payload(exc)
            source = _source(
                config=self.config,
                source_version=self._source_version(),
                query=query,
                raw_payload={
                    "query": query,
                    "error": raw_error,
                    "attempts": raw_error.get("attempts") if isinstance(raw_error, dict) else None,
                },
                cache_hit=False,
                limitations=[
                    f"Ensembl VEP online query failed: {exc.__class__.__name__}: {exc}",
                    *_error_limitations("Ensembl VEP", raw_error),
                    *_attempt_limitations(raw_error.get("attempts") if isinstance(raw_error, dict) else None),
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
                        *_attempt_limitations(raw_error.get("attempts") if isinstance(raw_error, dict) else None),
                        "No PP3/BP4 evidence is generated directly by VEP provider failure.",
                    ],
                )
            ]

    def _load_payload(self, query: dict[str, Any]) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        payload: list[dict[str, Any]] | None = None
        selected_stage: dict[str, Any] | None = None
        for full_stage, minimal_stage in _stage_groups(query):
            full_timeout = False
            try:
                payload = self._execute_stage(full_stage)
                attempts.append(_attempt_success(full_stage, payload))
                selected_stage = full_stage
                break
            except Exception as full_exc:  # noqa: BLE001 - fallback is provider-local.
                full_timeout = _is_timeout_error(full_exc)
                attempts.append(_attempt_error(full_stage, full_exc))
            try:
                payload = self._execute_stage(minimal_stage)
                attempts.append(_attempt_success(minimal_stage, payload))
                selected_stage = minimal_stage
                break
            except Exception as minimal_exc:  # noqa: BLE001
                attempts.append(_attempt_error(minimal_stage, minimal_exc))
                if full_timeout or _is_timeout_error(minimal_exc):
                    break
        else:
            payload = None
            selected_stage = None
        if payload is None or selected_stage is None:
            raise VEPProviderAttemptsError(
                "VEP provider attempts failed.",
                attempts=attempts,
                query=query,
            )
        return {
            "provider": "EnsemblVEPOnlineProvider",
            "source_version": self._source_version(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": ENSEMBL_VEP_ENDPOINT,
            "query": query,
            "attempts": attempts,
            "selected_variant_representation": selected_stage["variant_representation"],
            "selected_fallback_outcome": "minimal_consequence" if selected_stage["params_mode"] == "minimal" else "full_predictor",
            "request_method": selected_stage["method"],
            "request_url": selected_stage["request_url"],
            "payload": payload,
        }

    def _source_version(self) -> str:
        return self.config.source_version or "Ensembl REST VEP live"

    def _execute_stage(self, stage: dict[str, Any]) -> list[dict[str, Any]]:
        if stage["method"] == "POST":
            payload = self.http_client.post_json(stage["request_url"], stage["request_payload"])
        else:
            payload = self.http_client.get_json(stage["request_url"], params=stage["params"])
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"VEP response error: {payload.get('error')}")
        if not isinstance(payload, list):
            raise RuntimeError(f"VEP response was not a JSON array: {type(payload).__name__}")
        return payload


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
    if any(item.get("outcome") == "failure" for item in payload.get("attempts") or [] if isinstance(item, dict)):
        limitations.append("One or more VEP fallback attempts failed before a usable response was parsed.")
        limitations.extend(_attempt_limitations(payload.get("attempts") or []))
    if payload.get("selected_fallback_outcome") == "minimal_consequence":
        limitations.append(
            "VEP predictor-enriched request failed or was skipped; minimal consequence response was used."
        )
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
                raw_payload={
                    "record": record,
                    "transcript_consequence": consequence,
                    "retrieved_at": payload.get("retrieved_at"),
                    "endpoint": payload.get("endpoint"),
                    "request_method": payload.get("request_method"),
                    "request_url": payload.get("request_url"),
                    "selected_variant_representation": payload.get("selected_variant_representation"),
                    "selected_fallback_outcome": payload.get("selected_fallback_outcome"),
                    "attempts": payload.get("attempts") or [],
                },
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
                protein_change = consequence.get("hgvsp") or _protein_change_from_consequence(consequence)
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
                        protein_change=protein_change,
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
    protein_change = _protein_change_from_consequence(consequence)
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
                protein_change=consequence.get("hgvsp") or protein_change,
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
        request_method=raw_payload.get("request_method") or "GET",
        request_url=raw_payload.get("request_url") or ENSEMBL_VEP_ENDPOINT,
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
        "transcript": variant.transcript.accession if variant.transcript else None,
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


def _vep_params() -> dict[str, str]:
    return {
        "CADD": "1",
        "SpliceAI": "1",
        "AlphaMissense": "1",
    }


def _minimal_params() -> dict[str, str]:
    return {}


def _vcf_variant_line(query: dict[str, Any]) -> str:
    return f"{query['chrom']} {query['pos']} . {query['ref']} {query['alt']} . . ."


def _stage_groups(query: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    groups = []
    if _has_coordinate(query):
        post_payload = {"variants": [_vcf_variant_line(query)]}
        groups.append(
            (
                _stage(
                    name="POST region full predictors",
                    method="POST",
                    request_url=_url_with_params(ENSEMBL_VEP_ENDPOINT, _vep_params()),
                    request_payload=post_payload,
                    params={},
                    query=query,
                    variant_representation="vcf_line",
                    params_mode="full",
                ),
                _stage(
                    name="POST region minimal consequence",
                    method="POST",
                    request_url=ENSEMBL_VEP_ENDPOINT,
                    request_payload=post_payload,
                    params={},
                    query=query,
                    variant_representation="vcf_line",
                    params_mode="minimal",
                ),
            )
        )
        get_region = _get_region(query)
        groups.append(
            (
                _stage(
                    name="GET region full predictors",
                    method="GET",
                    request_url=f"{ENSEMBL_VEP_ENDPOINT}/{get_region}",
                    request_payload=None,
                    params=_vep_params(),
                    query=query,
                    variant_representation="region_alt_only",
                    params_mode="full",
                ),
                _stage(
                    name="GET region minimal consequence",
                    method="GET",
                    request_url=f"{ENSEMBL_VEP_ENDPOINT}/{get_region}",
                    request_payload=None,
                    params=_minimal_params(),
                    query=query,
                    variant_representation="region_alt_only",
                    params_mode="minimal",
                ),
            )
        )
    hgvs = query.get("hgvs_c")
    if hgvs:
        hgvs_url = f"{ENSEMBL_VEP_HGVS_ENDPOINT}/{quote(str(hgvs), safe='')}"
        groups.append(
            (
                _stage(
                    name="HGVS full predictors",
                    method="GET",
                    request_url=hgvs_url,
                    request_payload=None,
                    params=_vep_params(),
                    query=query,
                    variant_representation="transcript_hgvs",
                    params_mode="full",
                ),
                _stage(
                    name="HGVS minimal consequence",
                    method="GET",
                    request_url=hgvs_url,
                    request_payload=None,
                    params=_minimal_params(),
                    query=query,
                    variant_representation="transcript_hgvs",
                    params_mode="minimal",
                ),
            )
        )
    return groups


def _stage(
    *,
    name: str,
    method: str,
    request_url: str,
    request_payload: dict[str, Any] | None,
    params: dict[str, str],
    query: dict[str, Any],
    variant_representation: str,
    params_mode: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "method": method,
        "request_url": request_url,
        "request_payload": request_payload,
        "params": params,
        "query": query,
        "variant_representation": variant_representation,
        "params_mode": params_mode,
        "hgvs_c": query.get("hgvs_c"),
        "transcript": query.get("transcript"),
    }


def _has_coordinate(query: dict[str, Any]) -> bool:
    return all(query.get(key) not in {None, ""} for key in ("chrom", "pos", "ref", "alt"))


def _get_region(query: dict[str, Any]) -> str:
    return f"{query['chrom']}:{query['pos']}-{query['pos']}:1/{quote(str(query['alt']), safe='')}"


def _url_with_params(url: str, params: dict[str, str]) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params)}"


def _attempt_success(stage: dict[str, Any], payload: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **_attempt_base(stage),
        "outcome": "success",
        "records_count": len(payload),
    }


def _attempt_error(
    stage: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    error = _error_payload(exc)
    item = {
        **_attempt_base(stage),
        "outcome": "failure",
        "http_status": error.get("status"),
        "timeout": _is_timeout_error(exc),
        "error": error,
        "error_summary": _provider_error_summary(error),
    }
    return item


def _attempt_base(stage: dict[str, Any]) -> dict[str, Any]:
    request_payload = stage.get("request_payload")
    request_fingerprint = {
        "method": stage["method"],
        "request_url": stage["request_url"],
        "request_payload": request_payload,
        "params": stage.get("params") or {},
    }
    return {
        "name": stage["name"],
        "method": stage["method"],
        "endpoint": ENSEMBL_VEP_ENDPOINT if stage["variant_representation"] != "transcript_hgvs" else ENSEMBL_VEP_HGVS_ENDPOINT,
        "request_url": stage["request_url"],
        "request_payload": request_payload,
        "request_payload_hash": raw_record_hash(request_fingerprint),
        "variant_representation": stage["variant_representation"],
        "params_mode": stage["params_mode"],
        "hgvs_c": stage.get("hgvs_c"),
        "transcript": stage.get("transcript"),
    }


def _error_payload(exc: Exception) -> dict[str, Any]:
    if hasattr(exc, "to_payload"):
        payload = exc.to_payload()
        if isinstance(payload, dict):
            return payload
    return {
        "message": str(exc),
        "cause_type": exc.__class__.__name__,
    }


def _error_limitations(provider: str, payload: dict[str, Any]) -> list[str]:
    details = []
    if payload.get("attempts"):
        details.extend(_attempt_limitations(payload.get("attempts")))
    if payload.get("status") is not None:
        details.append(f"{provider} HTTP status: {payload['status']}.")
    if payload.get("response_text"):
        details.append(f"{provider} HTTP response body summary: {str(payload['response_text'])[:240]}")
    return details


def _attempt_limitations(attempts: Any) -> list[str]:
    limitations = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict) or attempt.get("outcome") != "failure":
            continue
        limitations.append(
            "VEP failed attempt: "
            f"{attempt.get('name')} via {attempt.get('method')} {attempt.get('variant_representation')} "
            f"status={attempt.get('http_status')} timeout={attempt.get('timeout')} "
            f"summary={attempt.get('error_summary')}"
        )
        error = attempt.get("error") if isinstance(attempt.get("error"), dict) else {}
        if error.get("response_text"):
            limitations.append(f"Ensembl VEP HTTP response body summary: {str(error['response_text'])[:240]}")
    return limitations


def _provider_error_summary(payload: dict[str, Any]) -> str:
    parts = []
    if payload.get("status") is not None:
        parts.append(f"HTTP {payload['status']}")
    if payload.get("message"):
        parts.append(str(payload["message"]))
    if payload.get("response_text"):
        parts.append(str(payload["response_text"])[:240])
    if payload.get("cause_type"):
        parts.append(str(payload["cause_type"]))
    return " | ".join(parts) or str(payload)[:240]


def _is_timeout_error(exc: Exception) -> bool:
    payload = _error_payload(exc)
    text = " ".join(
        str(item)
        for item in [payload.get("cause_type"), payload.get("message"), payload.get("response_text")]
        if item
    ).lower()
    return isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text


def _protein_change_from_consequence(consequence: dict[str, Any]) -> str | None:
    if consequence.get("hgvsp"):
        return str(consequence["hgvsp"])
    amino_acids = consequence.get("amino_acids")
    protein_start = consequence.get("protein_start")
    if not amino_acids or protein_start is None:
        return None
    parts = str(amino_acids).split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    ref = AA_THREE_LETTER.get(parts[0], parts[0])
    alt = AA_THREE_LETTER.get(parts[1], parts[1])
    if "frameshift_variant" in (consequence.get("consequence_terms") or []):
        return f"p.{ref}{protein_start}fs"
    if alt == "Ter":
        return f"p.{ref}{protein_start}Ter"
    return f"p.{ref}{protein_start}{alt}"
