from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.normalization import normalize_variant
from variant_pathogenicity_rater.schemas.common import AuditTrail
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


RunStep = Callable[[str, list[AuditTrail], list[str], Callable[[], Any]], Any | None]
AuditEventFactory = Callable[[str, str, list[str] | None], AuditTrail]


@dataclass(frozen=True)
class NormalizationPhaseResult:
    normalized_variant: Variant | None
    original_normalized_variant: Variant | None
    context: GeneDiseaseContext | None
    normalization_failed: bool


def run_normalization_phase(
    *,
    arguments: dict[str, Any],
    audit_trail: list[AuditTrail],
    limitations: list[str],
    step_results: dict[str, Any],
    run_step: RunStep,
    audit_event: AuditEventFactory,
) -> NormalizationPhaseResult:
    normalization_result = run_step(
        "normalize_variant",
        audit_trail,
        limitations,
        lambda: normalize_variant(_normalization_payload(arguments)),
    )
    if normalization_result is None or normalization_result.normalized_variant is None:
        return NormalizationPhaseResult(
            normalized_variant=None,
            original_normalized_variant=None,
            context=None,
            normalization_failed=True,
        )

    normalized_variant = normalization_result.normalized_variant
    step_results["normalize_variant"] = json.loads(normalization_result.model_dump_json())
    limitations.extend(normalization_result.normalization_warnings)

    context = _gene_disease_context(
        arguments,
        normalized_variant,
        limitations,
        audit_trail,
        audit_event,
    )
    return NormalizationPhaseResult(
        normalized_variant=normalized_variant,
        original_normalized_variant=normalized_variant,
        context=context,
        normalization_failed=False,
    )


def _normalization_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    variant = arguments.get("variant")
    if isinstance(variant, dict):
        payload = dict(variant)
    else:
        payload = dict(arguments)
        payload.pop("options", None)
        payload.pop("reviewed_evidence", None)

    aliases = {
        "gene": "gene_symbol",
        "chromosome": "chrom",
        "position": "pos",
    }
    for source, target in aliases.items():
        if source in arguments and target not in payload:
            payload[target] = arguments[source]

    for field in ["gene", "transcript", "hgvs_c", "hgvs_p", "chromosome", "position", "ref", "alt"]:
        if field in arguments and field not in payload:
            payload[field] = arguments[field]
    if "value" in payload and "hgvs" not in payload and "hgvs_c" not in payload:
        payload["hgvs"] = payload["value"]
    if "value" in arguments and "hgvs" not in payload and "hgvs_c" not in payload:
        payload["hgvs"] = arguments["value"]
    if "input_type" not in payload and "chrom" in payload and "pos" in payload:
        payload["input_type"] = "vcf_like"
    return payload


def _gene_disease_context(
    arguments: dict[str, Any],
    variant: Variant,
    limitations: list[str],
    audit_trail: list[AuditTrail],
    audit_event: AuditEventFactory,
) -> GeneDiseaseContext:
    context_payload = (
        arguments.get("gene_disease_context")
        or arguments.get("context")
        or arguments.get("options", {}).get("gene_disease_context")
        or {}
    )
    payload = dict(context_payload) if isinstance(context_payload, dict) else {}
    payload.setdefault("gene", arguments.get("gene") or variant.gene_symbol or "unknown")
    payload.setdefault("disease", arguments.get("disease") or "not provided")
    payload.setdefault("inheritance", arguments.get("inheritance"))
    phenotype = arguments.get("phenotype") or arguments.get("phenotype_terms")
    if phenotype and "phenotype_terms" not in payload:
        payload["phenotype_terms"] = phenotype if isinstance(phenotype, list) else [str(phenotype)]
    if variant.transcript and "transcript" not in payload:
        payload["transcript"] = variant.transcript.model_dump(mode="json")
    try:
        context = GeneDiseaseContext.model_validate(payload)
    except ValidationError as exc:
        limitations.append(f"gene_disease_context validation failed; fallback context used: {exc}")
        context = GeneDiseaseContext(
            gene=variant.gene_symbol or "unknown",
            disease_name="not provided",
        )
    audit_trail.append(
        audit_event(
            "build_gene_disease_context",
            "completed",
            ["Context may be incomplete and requires review."],
        )
    )
    return context
