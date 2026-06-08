from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from pydantic import Field

from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.schemas.common import SchemaModel


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "data" / "provider_benchmark" / "provider_benchmark_v1.json"
PROVIDERS = ("clinvar", "gnomad", "vep", "pubmed", "litvar")
OUTCOMES = ("success", "no_record", "failure", "partial", "skipped")


class ProviderOutcomeMetrics(SchemaModel):
    success: int = 0
    no_record: int = 0
    failure: int = 0
    partial: int = 0
    skipped: int = 0
    dependency_skipped: int = 0
    invalid_identity: int = 0
    missing_identity: int = 0


class ProviderYieldMetrics(SchemaModel):
    records_found: int = 0
    candidate_evidence_generated: int = 0
    af_records_found: int = 0
    population_provider_hits: int = 0
    consequence_resolved: int = 0
    predictor_records_returned: int = 0
    articles_found: int = 0
    summary_generated: int = 0
    citations_found: int = 0


class ProviderRuntimeMetrics(SchemaModel):
    avg_latency_ms: float = 0.0
    median_latency_ms: float = 0.0
    latency_scope: str = "unavailable"
    provider_latency_count: int = 0
    case_level_latency_used_count: int = 0
    timeout_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0


class ResolutionCoverageMetrics(SchemaModel):
    coordinate_resolution_rate_before: float = 0.0
    coordinate_resolution_rate_after: float = 0.0
    protein_resolution_rate_before: float = 0.0
    protein_resolution_rate_after: float = 0.0
    coordinate_available_before: int = 0
    coordinate_available_after: int = 0
    protein_available_before: int = 0
    protein_available_after: int = 0


class IdentityCoverageMetrics(SchemaModel):
    gnomad_variant_id_available: int = 0
    identity_conflict_count: int = 0
    coordinate_available: int = 0
    protein_available: int = 0


class ProviderCaseResult(SchemaModel):
    case_id: str
    gene: str
    status: str
    final_classification: str | None = None
    classification_unchanged_by_benchmark: bool = True
    provider_runtime: dict[str, Any] = Field(default_factory=dict)
    provider_yield: dict[str, Any] = Field(default_factory=dict)
    resolution_after: dict[str, bool] = Field(default_factory=dict)
    identity_coverage: dict[str, Any] = Field(default_factory=dict)
    runtime_ms: float = 0.0
    limitations: list[str] = Field(default_factory=list)


class ProviderBenchmarkResult(SchemaModel):
    dataset_id: str
    dataset_size: int
    clinvar: ProviderOutcomeMetrics
    gnomad: ProviderOutcomeMetrics
    vep: ProviderOutcomeMetrics
    pubmed: ProviderOutcomeMetrics
    litvar: ProviderOutcomeMetrics
    provider_yield: dict[str, ProviderYieldMetrics]
    runtime: dict[str, ProviderRuntimeMetrics]
    resolution_coverage: ResolutionCoverageMetrics
    identity_coverage: IdentityCoverageMetrics = Field(default_factory=IdentityCoverageMetrics)
    cases: list[ProviderCaseResult]
    summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


def run_provider_benchmark(
    *,
    dataset_path: str | Path | None = None,
    use_online: bool = False,
    include_litvar: bool = False,
    provider_cache_dir: str | None = None,
    provider_timeout: float | None = None,
    case_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> ProviderBenchmarkResult:
    dataset = _load_dataset(dataset_path or DEFAULT_DATASET)
    cases = list(dataset["cases"])
    runner = case_runner or rate_variant
    outcome_counts: dict[str, Counter[str]] = {provider: Counter() for provider in PROVIDERS}
    yield_metrics = {provider: ProviderYieldMetrics() for provider in PROVIDERS}
    latencies: dict[str, list[float]] = {provider: [] for provider in PROVIDERS}
    latency_scopes: dict[str, Counter[str]] = {provider: Counter() for provider in PROVIDERS}
    timeout_counts: Counter[str] = Counter()
    cache_hits: Counter[str] = Counter()
    cache_misses: Counter[str] = Counter()
    provider_diagnostics: dict[str, dict[str, Any]] = {
        provider: {
            "failure_case_ids": [],
            "no_record_case_ids": [],
            "dependency_skipped_case_ids": [],
            "invalid_identity_case_ids": [],
            "missing_identity_case_ids": [],
            "error_examples": [],
        }
        for provider in PROVIDERS
    }
    case_results: list[ProviderCaseResult] = []
    limitations: list[str] = []

    before_coordinate = sum(1 for case in cases if case["expected_resolution"]["coordinate_available"])
    before_protein = sum(1 for case in cases if case["expected_resolution"]["protein_available"])
    after_coordinate = 0
    after_protein = 0
    identity_totals = Counter()

    for case in cases:
        payload = _payload(case, use_online, include_litvar, provider_cache_dir, provider_timeout)
        started = time.perf_counter()
        try:
            result = runner(payload)
        except Exception as exc:  # noqa: BLE001 - benchmark failures are observable results.
            elapsed = (time.perf_counter() - started) * 1000
            failure_text = f"Benchmark case {case['case_id']} failed: {exc.__class__.__name__}: {exc}"
            limitations.append(failure_text)
            failed_case = ProviderCaseResult(
                case_id=case["case_id"],
                gene=case["gene"],
                status="error",
                provider_runtime={},
                runtime_ms=round(elapsed, 3),
                limitations=[failure_text],
            )
            case_results.append(failed_case)
            for provider in PROVIDERS:
                outcome_counts[provider]["failure"] += 1
                latencies[provider].append(elapsed)
                latency_scopes[provider]["case"] += 1
                _record_provider_diagnostic(
                    provider_diagnostics,
                    provider,
                    case["case_id"],
                    "failure",
                    {"error_type": exc.__class__.__name__, "error_message_summary": str(exc)},
                )
                if isinstance(exc, TimeoutError) or "timeout" in str(exc).lower():
                    timeout_counts[provider] += 1
            continue

        elapsed = float(result.get("benchmark_latency_ms", (time.perf_counter() - started) * 1000))
        resolution = _resolution_flags(result)
        identity_coverage = _identity_coverage(result)
        identity_totals["gnomad_variant_id_available"] += int(identity_coverage["gnomad_variant_id_available"])
        identity_totals["identity_conflict_count"] += int(identity_coverage["identity_conflict_count"])
        identity_totals["coordinate_available"] += int(identity_coverage["coordinate_available"])
        identity_totals["protein_available"] += int(identity_coverage["protein_available"])
        after_coordinate += int(resolution["coordinate_available"])
        after_protein += int(resolution["protein_available"])
        provider_runtime = _provider_runtime(result, include_litvar=include_litvar)
        provider_yield = _provider_yield(result)
        _accumulate_yield(yield_metrics, provider_yield)

        for provider in PROVIDERS:
            runtime_payload = provider_runtime.get(provider) or {}
            outcome = _normalize_outcome(runtime_payload.get("outcome"))
            outcome_counts[provider][outcome] += 1
            dependency_status = _dependency_status(runtime_payload)
            if dependency_status and dependency_status.get("satisfied") is False:
                outcome_counts[provider]["dependency_skipped"] += 1
                status = str(dependency_status.get("status") or "")
                if status == "invalid_identity":
                    outcome_counts[provider]["invalid_identity"] += 1
                if status == "missing_identity":
                    outcome_counts[provider]["missing_identity"] += 1
            _record_provider_diagnostic(provider_diagnostics, provider, case["case_id"], outcome, runtime_payload)
            provider_latency, latency_scope = _latency(runtime_payload, elapsed)
            if provider_latency is not None:
                latencies[provider].append(provider_latency)
                latency_scopes[provider][latency_scope] += 1
            if runtime_payload.get("cache_hit") is True:
                cache_hits[provider] += 1
            elif runtime_payload.get("cache_hit") is False:
                cache_misses[provider] += 1
            if _is_timeout(runtime_payload):
                timeout_counts[provider] += 1

        case_results.append(
            ProviderCaseResult(
                case_id=case["case_id"],
                gene=case["gene"],
                status=str(result.get("status") or "unknown"),
                final_classification=result.get("final_classification"),
                classification_unchanged_by_benchmark=True,
                provider_runtime=provider_runtime,
                provider_yield=provider_yield,
                resolution_after=resolution,
                identity_coverage=identity_coverage,
                runtime_ms=round(elapsed, 3),
                limitations=list(result.get("limitations") or []),
            )
        )

    runtime = {
        provider: _runtime_metrics(
            latencies[provider],
            latency_scopes[provider],
            timeout_counts[provider],
            cache_hits[provider],
            cache_misses[provider],
        )
        for provider in PROVIDERS
    }
    provider_outcomes = {
        provider: ProviderOutcomeMetrics(
            **{
                key: outcome_counts[provider][key]
                for key in (
                    *OUTCOMES,
                    "dependency_skipped",
                    "invalid_identity",
                    "missing_identity",
                )
            }
        )
        for provider in PROVIDERS
    }
    resolution = ResolutionCoverageMetrics(
        coordinate_available_before=before_coordinate,
        coordinate_available_after=after_coordinate,
        protein_available_before=before_protein,
        protein_available_after=after_protein,
        coordinate_resolution_rate_before=_rate(before_coordinate, len(cases)),
        coordinate_resolution_rate_after=_rate(after_coordinate, len(cases)),
        protein_resolution_rate_before=_rate(before_protein, len(cases)),
        protein_resolution_rate_after=_rate(after_protein, len(cases)),
    )
    summary = {
        "provider_with_most_failures": _provider_with_max(outcome_counts, "failure"),
        "least_stable_provider": _least_stable_provider(outcome_counts),
        "cases_with_failures": [
            case.case_id
            for case in case_results
            if any(_normalize_outcome((case.provider_runtime.get(provider) or {}).get("outcome")) == "failure" for provider in PROVIDERS)
            or case.status == "error"
        ],
        "classification_benchmark": False,
        "provider_diagnostics": provider_diagnostics,
    }
    return ProviderBenchmarkResult(
        dataset_id=str(dataset.get("dataset_id") or "provider_benchmark"),
        dataset_size=len(cases),
        clinvar=provider_outcomes["clinvar"],
        gnomad=provider_outcomes["gnomad"],
        vep=provider_outcomes["vep"],
        pubmed=provider_outcomes["pubmed"],
        litvar=provider_outcomes["litvar"],
        provider_yield=yield_metrics,
        runtime=runtime,
        resolution_coverage=resolution,
        identity_coverage=IdentityCoverageMetrics(
            gnomad_variant_id_available=identity_totals["gnomad_variant_id_available"],
            identity_conflict_count=identity_totals["identity_conflict_count"],
            coordinate_available=identity_totals["coordinate_available"],
            protein_available=identity_totals["protein_available"],
        ),
        cases=case_results,
        summary=summary,
        limitations=_unique(limitations),
    )


def render_provider_benchmark_report(result: ProviderBenchmarkResult) -> str:
    lines = [
        "# Real-World Provider Benchmark Report",
        "",
        f"Dataset: {result.dataset_size} variants",
        "",
    ]
    for provider in PROVIDERS:
        metrics = getattr(result, provider)
        lines.extend(
            [
                f"## {provider}",
                f"- success: {metrics.success}",
                f"- no_record: {metrics.no_record}",
                f"- failure: {metrics.failure}",
                f"- partial: {metrics.partial}",
                f"- skipped: {metrics.skipped}",
                f"- dependency_skipped: {metrics.dependency_skipped}",
                f"- invalid_identity: {metrics.invalid_identity}",
                f"- missing_identity: {metrics.missing_identity}",
                "",
            ]
        )
    resolution = result.resolution_coverage
    identity = result.identity_coverage
    lines.extend(
        [
            "## Resolution improvement",
            f"- coordinate: {resolution.coordinate_available_before}/{result.dataset_size} -> {resolution.coordinate_available_after}/{result.dataset_size}",
            f"- protein: {resolution.protein_available_before}/{result.dataset_size} -> {resolution.protein_available_after}/{result.dataset_size}",
            "",
            "## Provider identity coverage",
            f"- gnomad_variant_id_available: {identity.gnomad_variant_id_available}/{result.dataset_size}",
            f"- identity_conflict_count: {identity.identity_conflict_count}",
            f"- coordinate_available: {identity.coordinate_available}/{result.dataset_size}",
            f"- protein_available: {identity.protein_available}/{result.dataset_size}",
            "",
            "## Runtime",
        ]
    )
    for provider, runtime in result.runtime.items():
        lines.append(
            f"- {provider}: avg={runtime.avg_latency_ms:.2f} ms, median={runtime.median_latency_ms:.2f} ms, scope={runtime.latency_scope}, provider_samples={runtime.provider_latency_count}, case_level_samples={runtime.case_level_latency_used_count}, timeouts={runtime.timeout_count}"
        )
    lines.extend(["", "## Cache"])
    for provider, runtime in result.runtime.items():
        lines.append(
            f"- {provider}: hits={runtime.cache_hit_count}, misses={runtime.cache_miss_count}"
        )
    lines.extend(["", "## Provider diagnostics"])
    diagnostics = result.summary.get("provider_diagnostics") or {}
    for provider in PROVIDERS:
        payload = diagnostics.get(provider) or {}
        lines.append(f"- {provider} failures: {', '.join(payload.get('failure_case_ids') or []) or 'none'}")
        lines.append(f"- {provider} no_record: {', '.join(payload.get('no_record_case_ids') or []) or 'none'}")
        lines.append(f"- {provider} dependency_skipped: {', '.join(payload.get('dependency_skipped_case_ids') or []) or 'none'}")
        if provider == "gnomad":
            lines.append(
                f"- gnomAD skipped due to invalid identity: {', '.join(payload.get('invalid_identity_case_ids') or []) or 'none'}"
            )
        for example in (payload.get("error_examples") or [])[:3]:
            lines.append(
                f"- {provider} error example: {example.get('case_id')} {example.get('error_type') or 'ProviderFailure'} - {example.get('error_message_summary') or ''}"
            )
    lines.extend(
        [
            "",
            "## Safety",
            "- This is a provider benchmark, not an ACMG truth benchmark.",
            "- Benchmark metrics do not change classification or evidence generation.",
        ]
    )
    return "\n".join(lines)


def write_provider_benchmark_report(result: ProviderBenchmarkResult, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_provider_benchmark_report(result), encoding="utf-8")
    return output_path


def _load_dataset(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _payload(
    case: dict[str, Any],
    use_online: bool,
    include_litvar: bool,
    provider_cache_dir: str | None,
    provider_timeout: float | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "mock_mode": True,
        "include_literature": bool(use_online),
    }
    if use_online:
        options.update(
            {
                "use_online_clinvar": True,
                "use_online_gnomad": True,
                "use_online_vep": True,
                "use_online_pubmed": True,
                "use_online_litvar": bool(include_litvar),
            }
        )
    if provider_cache_dir:
        options["provider_cache_dir"] = provider_cache_dir
    if provider_timeout is not None:
        options["provider_timeout"] = provider_timeout
    return {
        "gene": case["gene"],
        "transcript": case["transcript"],
        "hgvs_c": case["hgvs_c"],
        "options": options,
    }


def _provider_runtime(result: dict[str, Any], *, include_litvar: bool) -> dict[str, Any]:
    runtime = ((result.get("step_results") or {}).get("provider_runtime") or {})
    literature = runtime.get("literature")
    return {
        "clinvar": dict(runtime.get("clinvar") or {}),
        "gnomad": dict(runtime.get("population") or {}),
        "vep": dict(runtime.get("computational") or {}),
        "pubmed": _literature_runtime(literature, "PubMed"),
        "litvar": (
            _literature_runtime(literature, "LitVar")
            if include_litvar
            else {"provider_name": "LitVar", "outcome": "skipped", "attempted": False, "records_count": 0}
        ),
    }


def _literature_runtime(value: Any, provider_name: str) -> dict[str, Any]:
    payload = dict(value or {})
    payload["provider_name"] = provider_name
    return payload


def _provider_yield(result: dict[str, Any]) -> dict[str, Any]:
    clinvar = (result.get("step_results") or {}).get("query_clinvar") or {}
    population = (result.get("step_results") or {}).get("query_population_frequency") or {}
    computational = (result.get("step_results") or {}).get("evaluate_computational_evidence") or {}
    literature = (
        (result.get("step_results") or {}).get("search_and_summarize_literature")
        or (result.get("step_results") or {}).get("search_literature_evidence")
        or {}
    )
    predictor_calls = ((computational.get("summary") or {}).get("predictor_calls") or [])
    literature_records = _literature_records(literature)
    return {
        "clinvar": {
            "records_found": len(clinvar.get("records") or []),
            "candidate_evidence_generated": len(clinvar.get("candidate_evidence_items") or []),
        },
        "gnomad": {
            "af_records_found": int(population.get("overall_af") is not None or population.get("max_pop_af") is not None),
            "population_provider_hits": int(population.get("data_source") not in {None, "mock_population_frequency"} and bool(population)),
        },
        "vep": {
            "consequence_resolved": int(_vep_consequence_resolved(result)),
            "predictor_records_returned": len(predictor_calls),
        },
        "pubmed": {
            "articles_found": sum(1 for record in literature_records if _source_name(record) == "pubmed"),
            "summary_generated": int(bool(literature.get("criterion_summaries") or literature.get("summary"))),
        },
        "litvar": {
            "citations_found": sum(1 for record in literature_records if _source_name(record) == "litvar"),
        },
    }


def _identity_coverage(result: dict[str, Any]) -> dict[str, Any]:
    identity = result.get("provider_identity") or ((result.get("variant") or {}).get("provider_identity") or {})
    if not isinstance(identity, dict):
        identity = {}
    return {
        "gnomad_variant_id_available": bool(identity.get("gnomad_variant_id")),
        "identity_conflict_count": len(identity.get("identity_conflicts") or []),
        "coordinate_available": all(identity.get(field) for field in ("genome_build", "chrom", "pos", "ref", "alt")),
        "protein_available": bool(identity.get("hgvs_p") or identity.get("protein_change")),
    }


def _dependency_status(payload: dict[str, Any]) -> dict[str, Any] | None:
    dependency = payload.get("dependency_status")
    if isinstance(dependency, dict):
        return dependency
    provenance = payload.get("provenance")
    if isinstance(provenance, dict) and isinstance(provenance.get("provider_dependency"), dict):
        return provenance["provider_dependency"]
    return None


def _accumulate_yield(
    totals: dict[str, ProviderYieldMetrics],
    observed: dict[str, Any],
) -> None:
    for provider, payload in observed.items():
        metric = totals[provider]
        update = metric.model_dump()
        for key, value in payload.items():
            if key in update:
                update[key] = int(update[key]) + int(value or 0)
        totals[provider] = ProviderYieldMetrics(**update)


def _resolution_flags(result: dict[str, Any]) -> dict[str, bool]:
    variant = result.get("variant") or {}
    protein = variant.get("protein_resolution") or ((result.get("variant_resolution") or {}).get("resolved_hgvs_p") or {})
    coordinate = variant.get("coordinate_resolution") or ((result.get("variant_resolution") or {}).get("resolved_coordinate") or {})
    return {
        "coordinate_available": all(coordinate.get(key) for key in ("chrom", "pos", "ref", "alt")),
        "protein_available": bool(protein.get("hgvs_p")),
        "consequence_available": bool(protein.get("consequence")),
    }


def _runtime_metrics(
    latencies: list[float],
    scopes: Counter[str],
    timeout_count: int,
    cache_hit_count: int,
    cache_miss_count: int,
) -> ProviderRuntimeMetrics:
    provider_count = scopes["provider"]
    case_count = scopes["case"]
    if provider_count and case_count:
        latency_scope = "mixed"
    elif provider_count:
        latency_scope = "provider"
    elif case_count:
        latency_scope = "case"
    else:
        latency_scope = "unavailable"
    return ProviderRuntimeMetrics(
        avg_latency_ms=round(statistics.fmean(latencies), 3) if latencies else 0.0,
        median_latency_ms=round(statistics.median(latencies), 3) if latencies else 0.0,
        latency_scope=latency_scope,
        provider_latency_count=provider_count,
        case_level_latency_used_count=case_count,
        timeout_count=timeout_count,
        cache_hit_count=cache_hit_count,
        cache_miss_count=cache_miss_count,
    )


def _normalize_outcome(value: Any) -> str:
    text = str(value or "skipped")
    if text == "cache_hit":
        return "success"
    if text == "unavailable":
        return "failure"
    return text if text in OUTCOMES else "failure"


def _latency(payload: dict[str, Any], fallback: float) -> tuple[float | None, str]:
    if not payload.get("attempted"):
        return None, "unavailable"
    for key in ("latency_ms", "runtime_ms", "elapsed_ms"):
        if payload.get(key) is not None:
            return float(payload[key]), "provider"
    return fallback, "case"


def _record_provider_diagnostic(
    diagnostics: dict[str, dict[str, Any]],
    provider: str,
    case_id: str,
    outcome: str,
    payload: dict[str, Any],
) -> None:
    item = diagnostics[provider]
    dependency_status = _dependency_status(payload)
    if dependency_status and dependency_status.get("satisfied") is False:
        if case_id not in item["dependency_skipped_case_ids"]:
            item["dependency_skipped_case_ids"].append(case_id)
        status = str(dependency_status.get("status") or "")
        if status == "invalid_identity" and case_id not in item["invalid_identity_case_ids"]:
            item["invalid_identity_case_ids"].append(case_id)
        if status == "missing_identity" and case_id not in item["missing_identity_case_ids"]:
            item["missing_identity_case_ids"].append(case_id)
    if outcome == "failure":
        if case_id not in item["failure_case_ids"]:
            item["failure_case_ids"].append(case_id)
        if len(item["error_examples"]) < 3:
            item["error_examples"].append(
                {
                    "case_id": case_id,
                    "error_type": payload.get("error_type"),
                    "error_message_summary": payload.get("error_message_summary")
                    or "; ".join(str(value) for value in (payload.get("limitations") or [])[:2]),
                }
            )
    elif outcome == "no_record" and case_id not in item["no_record_case_ids"]:
        item["no_record_case_ids"].append(case_id)


def _is_timeout(payload: dict[str, Any]) -> bool:
    text = " ".join(
        str(item)
        for item in [
            payload.get("error_type"),
            payload.get("error_message_summary"),
            *(payload.get("limitations") or []),
        ]
        if item
    ).lower()
    return "timeout" in text or "timed out" in text


def _literature_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("literature_records", "literature_search_results", "records"):
        records = payload.get(key)
        if isinstance(records, list):
            return [record for record in records if isinstance(record, dict)]
    return []


def _source_name(record: dict[str, Any]) -> str:
    source = record.get("source")
    if isinstance(source, dict):
        source = source.get("name") or source.get("source")
    return str(source or record.get("data_source") or "").lower()


def _vep_consequence_resolved(result: dict[str, Any]) -> bool:
    protein = (result.get("variant") or {}).get("protein_resolution") or {}
    return bool(protein.get("consequence"))


def _provider_with_max(counts: dict[str, Counter[str]], key: str) -> str | None:
    values = [(provider, counter[key]) for provider, counter in counts.items()]
    provider, value = max(values, key=lambda item: item[1])
    return provider if value > 0 else None


def _least_stable_provider(counts: dict[str, Counter[str]]) -> str | None:
    scored = []
    for provider, counter in counts.items():
        unstable = counter["failure"] + counter["partial"]
        scored.append((provider, unstable))
    provider, score = max(scored, key=lambda item: item[1])
    return provider if score > 0 else None


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
