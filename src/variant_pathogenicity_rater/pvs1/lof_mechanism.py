from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from variant_pathogenicity_rater.pvs1.online_resolvers import resolve_online_lof_mechanism
from variant_pathogenicity_rater.pvs1.schema import LoFMechanismAssessment, PVS1Config
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


def resolve_lof_mechanism(
    variant: Variant,
    context: GeneDiseaseContext,
    *,
    config: PVS1Config | None = None,
    manual_overrides: dict[str, Any] | None = None,
) -> LoFMechanismAssessment:
    config = config or PVS1Config()
    if manual_overrides and "lof_is_known_mechanism" in manual_overrides:
        value = manual_overrides.get("lof_is_known_mechanism")
        return LoFMechanismAssessment(
            status="known" if value is True else "not_known" if value is False else "unknown",
            lof_is_known=value if isinstance(value, bool) else None,
            confidence=0.9 if isinstance(value, bool) else 0.2,
            source="manual_context",
            provenance=[{"source": "manual_context", "field": "lof_is_known_mechanism"}],
        )
    if context.lof_is_known_mechanism is not None:
        value = context.lof_is_known_mechanism
        return LoFMechanismAssessment(
            status="known" if value else "not_known",
            lof_is_known=value,
            confidence=0.85,
            source="manual_context",
            provenance=[{"source": context.source or "gene_disease_context"}],
        )

    curated = _resolve_local(context.gene_symbol or variant.gene_symbol, context.disease_name, context.inheritance_mode)
    if curated is not None:
        return curated

    if config.enable_online_resolvers:
        online = resolve_online_lof_mechanism(
            gene=context.gene_symbol or variant.gene_symbol,
            disease=context.disease_name,
            inheritance=context.inheritance_mode,
            config=config,
        )
        if online.status != "unknown" or online.limitations:
            return online

    return LoFMechanismAssessment(
        status="unknown",
        lof_is_known=None,
        confidence=0.0,
        source="unknown",
        limitations=["LoF mechanism is unknown for this gene-disease context."],
    )


def _resolve_local(
    gene: str | None,
    disease: str | None,
    inheritance: str | None,
) -> LoFMechanismAssessment | None:
    if not gene or not disease:
        return None
    gene_norm = gene.strip().upper()
    disease_norm = _norm(disease)
    inheritance_norm = _norm(inheritance)
    matches = []
    for row in _load_table():
        if str(row.get("gene", "")).upper() != gene_norm:
            continue
        if _norm(row.get("disease")) not in disease_norm and disease_norm not in _norm(row.get("disease")):
            continue
        matches.append(row)
    if not matches:
        return None
    exact = [row for row in matches if not inheritance_norm or _norm(row.get("inheritance")) == inheritance_norm]
    selected = exact[0] if exact else matches[0]
    limitations = list(selected.get("limitations") or [])
    if len(matches) > 1:
        limitations.append("Multiple local gene-disease mechanism rows matched; manual mechanism review is required.")
    lof = selected.get("lof_is_known_mechanism")
    status = "context_dependent" if selected.get("context_dependent") else "known" if lof else "not_known"
    return LoFMechanismAssessment(
        status=status,
        lof_is_known=bool(lof) if isinstance(lof, bool) else None,
        confidence=float(selected.get("confidence") or 0.7),
        source="local_curated",
        provenance=[{"source": "data/curated_lof_mechanisms.json", "record": selected}],
        limitations=limitations,
    )


def _load_table() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[3] / "data" / "curated_lof_mechanisms.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    return data if isinstance(data, list) else []


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())
