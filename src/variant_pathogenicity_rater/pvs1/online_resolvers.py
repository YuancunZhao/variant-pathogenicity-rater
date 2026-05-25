from __future__ import annotations

from pathlib import Path

from variant_pathogenicity_rater.data_sources.cache import DiskCache
from variant_pathogenicity_rater.pvs1.schema import LoFMechanismAssessment, PVS1Config


def resolve_online_lof_mechanism(
    *,
    gene: str | None,
    disease: str | None,
    inheritance: str | None,
    config: PVS1Config,
) -> LoFMechanismAssessment:
    query = {"gene": gene, "disease": disease, "inheritance": inheritance}
    cache_dir = Path(config.cache_dir or ".vpr_cache/pvs1")
    try:
        cache = DiskCache(cache_dir, ttl_seconds=7 * 24 * 60 * 60)
        entry, cache_hit = cache.get_or_set(
            provider="pvs1_lof_mechanism_online_placeholder",
            mode="online_optional",
            source_version="placeholder-v1",
            query=query,
            loader=lambda: {
                "resolved": False,
                "note": "Online ClinGen/OMIM/MedGen resolver placeholder; no external request implemented.",
            },
        )
        return LoFMechanismAssessment(
            status="unknown",
            lof_is_known=None,
            confidence=0.0,
            source="online_optional",
            provenance=[
                {
                    "provider": entry.provider,
                    "cache_key": entry.key,
                    "cache_hit": cache_hit,
                    "raw_record_hash": entry.raw_record_hash,
                    "query": query,
                }
            ],
            limitations=["Online LoF mechanism resolver is opt-in and currently returned no curated mechanism."],
        )
    except Exception as exc:  # noqa: BLE001 - online failures must never break rating.
        return LoFMechanismAssessment(
            status="unknown",
            lof_is_known=None,
            confidence=0.0,
            source="online_optional",
            limitations=[f"Online LoF mechanism resolution failed and was ignored: {exc.__class__.__name__}: {exc}"],
        )
