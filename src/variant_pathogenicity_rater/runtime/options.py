from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel


ONLINE_PROVIDER_MAPPINGS: dict[str, tuple[str, str, str]] = {
    "use_online_clinvar": ("clinvar", "clinvar", "NCBI ClinVar E-utilities live"),
    "use_online_gnomad": ("population", "gnomad", "gnomAD gnomad_r4 live GraphQL"),
    "use_online_vep": ("computational", "vep", "Ensembl REST VEP live"),
    "use_online_pubmed": ("literature", "literature", "PubMed/LitVar live"),
    "use_online_litvar": ("literature", "literature", "PubMed/LitVar live"),
}


CORE_OPTION_FIELDS = {
    "use_online_clinvar",
    "use_online_gnomad",
    "use_online_vep",
    "use_online_pubmed",
    "use_online_litvar",
    "provider_cache_dir",
    "provider_timeout",
    "provider_email",
    "provider_user_agent",
    "report_language",
    "report_mode",
    "disease",
    "inheritance",
    "confirmed_context",
    "reviewed_context",
    "reviewed_evidence",
    "supplemental_evidence_items",
    "mock_mode",
    "option_sources",
    "normalization_warnings",
    "passthrough_options",
}


class RuntimeOptions(SchemaModel):
    use_online_clinvar: bool = False
    use_online_gnomad: bool = False
    use_online_vep: bool = False
    use_online_pubmed: bool = False
    use_online_litvar: bool = False
    provider_cache_dir: str | None = None
    provider_timeout: float | None = None
    provider_email: str | None = None
    provider_user_agent: str | None = None
    report_language: str | None = None
    report_mode: str | None = None
    disease: str | None = None
    inheritance: str | None = None
    confirmed_context: dict[str, Any] | None = None
    reviewed_evidence: Any = None
    supplemental_evidence_items: Any = None
    mock_mode: bool = True
    option_sources: dict[str, str] = Field(default_factory=dict)
    normalization_warnings: list[str] = Field(default_factory=list)
    passthrough_options: dict[str, Any] = Field(default_factory=dict)


def normalize_runtime_options(
    options: Mapping[str, Any] | None = None,
    top_level: Mapping[str, Any] | None = None,
    source: str = "python_api",
) -> RuntimeOptions:
    payload = _runtime_payload_from_mapping(options or {}, source=source)
    warnings = list(payload.get("normalization_warnings") or [])
    option_sources = dict(payload.get("option_sources") or {})

    top = top_level or {}
    for key in ("disease", "inheritance", "confirmed_context"):
        if key in top and top.get(key) is not None:
            payload[key] = top.get(key)
            option_sources.setdefault(key, "top_level")

    if "reviewed_context" in top and top.get("reviewed_context") is not None:
        if payload.get("confirmed_context") is None:
            payload["confirmed_context"] = top.get("reviewed_context")
            option_sources.setdefault("confirmed_context", "top_level.reviewed_context")

    top_level_has_reviewed = "reviewed_evidence" in top
    options_has_reviewed = "reviewed_evidence" in (options or {})
    if top_level_has_reviewed:
        if options_has_reviewed:
            warnings.append(
                "Both top-level reviewed_evidence and options.reviewed_evidence were supplied; "
                "top-level reviewed_evidence was used."
            )
        payload["reviewed_evidence"] = top.get("reviewed_evidence")
        option_sources["reviewed_evidence"] = "top_level"

    payload["option_sources"] = option_sources
    payload["normalization_warnings"] = _unique(warnings)
    runtime_options = RuntimeOptions.model_validate(payload)
    return apply_online_provider_modes(runtime_options)


def merge_runtime_options(
    base: RuntimeOptions | Mapping[str, Any] | None,
    override: RuntimeOptions | Mapping[str, Any] | None,
    source: str,
) -> RuntimeOptions:
    base_runtime = (
        base
        if isinstance(base, RuntimeOptions)
        else normalize_runtime_options(base or {}, source="base")
    )
    override_runtime = (
        override
        if isinstance(override, RuntimeOptions)
        else normalize_runtime_options(override or {}, source=source)
    )
    merged = runtime_options_to_pipeline_dict(base_runtime)
    merged.update(runtime_options_to_pipeline_dict(override_runtime))
    merged_sources = dict(base_runtime.option_sources)
    for key in runtime_options_to_pipeline_dict(override_runtime):
        merged_sources[key] = source
    merged["option_sources"] = merged_sources
    return normalize_runtime_options(merged, source=source)


def runtime_options_to_pipeline_dict(runtime_options: RuntimeOptions) -> dict[str, Any]:
    payload = dict(runtime_options.passthrough_options)
    for key in (
        "use_online_clinvar",
        "use_online_gnomad",
        "use_online_vep",
        "use_online_pubmed",
        "use_online_litvar",
    ):
        value = getattr(runtime_options, key)
        if value:
            payload[key] = value
        else:
            payload.pop(key, None)

    optional_fields = (
        "provider_cache_dir",
        "provider_timeout",
        "provider_email",
        "provider_user_agent",
        "report_language",
        "report_mode",
        "disease",
        "inheritance",
        "confirmed_context",
        "reviewed_evidence",
        "supplemental_evidence_items",
    )
    for key in optional_fields:
        value = getattr(runtime_options, key)
        if value is not None:
            payload[key] = value
        else:
            payload.pop(key, None)

    payload["mock_mode"] = bool(runtime_options.mock_mode)
    if runtime_options.option_sources:
        payload["option_sources"] = dict(runtime_options.option_sources)
    else:
        payload.pop("option_sources", None)
    if runtime_options.normalization_warnings:
        payload["normalization_warnings"] = list(runtime_options.normalization_warnings)
    else:
        payload.pop("normalization_warnings", None)
    return payload


def apply_online_provider_modes(runtime_options: RuntimeOptions) -> RuntimeOptions:
    payload = runtime_options_to_pipeline_dict(runtime_options)
    data_sources = dict(payload.get("data_sources") or {})
    sources = dict(data_sources.get("sources") or data_sources.get("data_sources") or {})
    cache_root = runtime_options.provider_cache_dir
    for flag, (source_name, cache_name, live_source_version) in ONLINE_PROVIDER_MAPPINGS.items():
        if not getattr(runtime_options, flag):
            continue
        source = dict(sources.get(source_name) or {})
        source.update({"mode": "online", "online_enabled": True})
        if not source.get("source_version"):
            source["source_version"] = live_source_version
        if cache_root and not source.get("cache_dir"):
            source["cache_dir"] = f"{str(cache_root).rstrip('/')}/{cache_name}"
        sources[source_name] = source
    if sources:
        data_sources["sources"] = sources
        payload["data_sources"] = data_sources
    return _runtime_from_pipeline_payload(payload, runtime_options)


def _runtime_payload_from_mapping(options: Mapping[str, Any], source: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mock_mode": bool(options.get("mock_mode", True)),
        "option_sources": dict(options.get("option_sources") or {}),
        "normalization_warnings": list(options.get("normalization_warnings") or []),
        "passthrough_options": {},
    }
    for key in (
        "use_online_clinvar",
        "use_online_gnomad",
        "use_online_vep",
        "use_online_pubmed",
        "use_online_litvar",
    ):
        payload[key] = bool(options.get(key, False))

    for key in (
        "provider_cache_dir",
        "provider_timeout",
        "provider_email",
        "provider_user_agent",
        "report_language",
        "report_mode",
        "disease",
        "inheritance",
        "confirmed_context",
        "reviewed_evidence",
        "supplemental_evidence_items",
    ):
        if key in options:
            payload[key] = options.get(key)

    if "reviewed_context" in options and payload.get("confirmed_context") is None:
        payload["confirmed_context"] = options.get("reviewed_context")
        payload["option_sources"].setdefault("confirmed_context", f"{source}.reviewed_context")

    if "mock_supplemental_evidence_items" in options:
        payload["supplemental_evidence_items"] = options.get("mock_supplemental_evidence_items")
        payload["option_sources"].setdefault(
            "supplemental_evidence_items",
            f"{source}.mock_supplemental_evidence_items",
        )

    passthrough = dict(options.get("passthrough_options") or {})
    for key, value in options.items():
        if key not in CORE_OPTION_FIELDS:
            passthrough[key] = value
    payload["passthrough_options"] = passthrough
    for key in options:
        if key != "passthrough_options":
            payload["option_sources"].setdefault(key, source)
    return payload


def _runtime_from_pipeline_payload(
    payload: dict[str, Any],
    previous: RuntimeOptions,
) -> RuntimeOptions:
    normalized = _runtime_payload_from_mapping(payload, source="runtime_options")
    normalized["option_sources"] = dict(previous.option_sources)
    normalized["normalization_warnings"] = list(previous.normalization_warnings)
    return RuntimeOptions.model_validate(normalized)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        text = str(item)
        if text in seen:
            continue
        seen.add(text)
        unique_items.append(text)
    return unique_items
