from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.normalization import normalize_variant
from variant_pathogenicity_rater.resolution.provider_result import ResolutionProviderResult
from variant_pathogenicity_rater.variant_resolution import resolve_variant


def resolve_hgvs_to_variant(
    *,
    transcript: str | None,
    hgvs_c: str,
    gene: str | None = None,
    options: dict[str, Any] | None = None,
) -> ResolutionProviderResult:
    """Resolve transcript HGVS c. through the local resolution layer.

    This function is resolution-only. It does not generate ACMG evidence and it
    never raises provider failures to callers.
    """

    payload: dict[str, Any] = {"hgvs_c": hgvs_c}
    if transcript:
        payload["transcript"] = transcript
    if gene:
        payload["gene"] = gene
    try:
        normalization = normalize_variant(payload)
        if normalization.normalized_variant is None:
            return ResolutionProviderResult(
                provider="local_hgvs_resolution",
                outcome="failure",
                limitations=[
                    "HGVS input could not be normalized before resolution.",
                    *normalization.normalization_warnings,
                ],
            )
        result = resolve_variant(normalization.normalized_variant, options=options or {})
        return ResolutionProviderResult(
            provider=result.resolution_runtime.get("provider") or "local_hgvs_resolution",
            outcome=result.outcome,
            source_version=result.resolution_runtime.get("source_version"),
            cache_hit=result.resolution_runtime.get("cache_hit"),
            confidence=result.confidence,
            result=result.model_dump(mode="json"),
            provenance={"scope": "variant resolution only; not ACMG evidence"},
            limitations=result.limitations,
        )
    except Exception as exc:  # noqa: BLE001 - provider failures are limitations.
        return ResolutionProviderResult(
            provider="local_hgvs_resolution",
            outcome="failure",
            limitations=[f"HGVS resolution provider failed: {exc.__class__.__name__}: {exc}"],
        )
