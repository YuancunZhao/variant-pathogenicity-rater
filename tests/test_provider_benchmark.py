from __future__ import annotations

from pathlib import Path
from typing import Any

from variant_pathogenicity_rater.benchmark.provider_benchmark import (
    render_provider_benchmark_report,
    run_provider_benchmark,
    write_provider_benchmark_report,
)


def _result(
    *,
    case_id: str,
    clinvar: str = "success",
    gnomad: str = "no_record",
    vep: str = "partial",
    literature: str = "success",
    cache_hit: bool | None = None,
    latency_ms: float = 10.0,
    include_provider_latency: bool = True,
) -> dict[str, Any]:
    def latency(value: float) -> dict[str, float]:
        return {"latency_ms": value} if include_provider_latency else {}

    return {
        "status": "ok",
        "final_classification": "vus",
        "variant": {
            "protein_resolution": {
                "hgvs_p": "NP_000001.1:p.Ala1Gly",
                "consequence": "missense_variant",
            },
            "coordinate_resolution": {
                "chrom": "1",
                "pos": 100,
                "ref": "A",
                "alt": "G",
            },
        },
        "limitations": [],
        "benchmark_latency_ms": latency_ms,
        "step_results": {
            "provider_runtime": {
                "clinvar": {
                    "outcome": clinvar,
                    "records_count": 1 if clinvar == "success" else 0,
                    "attempted": clinvar != "skipped",
                    "cache_hit": cache_hit,
                    **latency(latency_ms),
                },
                "population": {
                    "outcome": gnomad,
                    "records_count": 1 if gnomad == "success" else 0,
                    "attempted": gnomad != "skipped",
                    "cache_hit": cache_hit,
                    "error_type": "gnomAD_online_query" if gnomad == "failure" else None,
                    "error_message_summary": "gnomAD online query failed: mocked" if gnomad == "failure" else None,
                    **latency(latency_ms + 1),
                },
                "computational": {
                    "outcome": vep,
                    "records_count": 2 if vep in {"success", "partial"} else 0,
                    "attempted": vep != "skipped",
                    "cache_hit": cache_hit,
                    "error_type": "Ensembl_VEP_online_query" if vep == "failure" else None,
                    "error_message_summary": "Ensembl VEP online query failed: mocked" if vep == "failure" else None,
                    **latency(latency_ms + 2),
                    "limitations": ["partial predictor payload"] if vep == "partial" else [],
                },
                "literature": {
                    "outcome": literature,
                    "records_count": 2 if literature == "success" else 0,
                    "attempted": literature != "skipped",
                    "cache_hit": cache_hit,
                    **latency(latency_ms + 3),
                },
            },
            "query_clinvar": {
                "records": [{"id": case_id}] if clinvar == "success" else [],
                "candidate_evidence_items": [{"code": "PP5"}] if clinvar == "success" else [],
            },
            "query_population_frequency": {
                "data_source": "gnomAD",
                "overall_af": 0.001 if gnomad == "success" else None,
            },
            "evaluate_computational_evidence": {
                "summary": {
                    "predictor_calls": [{"method": "CADD"}, {"method": "REVEL"}]
                    if vep in {"success", "partial"}
                    else []
                }
            },
            "search_and_summarize_literature": {
                "literature_records": [
                    {"source": "PubMed", "pmid": "1"},
                    {"source": "LitVar", "pmid": "2"},
                ]
                if literature == "success"
                else [],
                "criterion_summaries": [{"criterion": "PS4"}] if literature == "success" else [],
            },
        },
    }


def test_provider_benchmark_counts_outcomes_yield_runtime_and_cache(tmp_path: Path) -> None:
    calls = {"count": 0}

    def runner(payload: dict[str, Any]) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            return _result(case_id=payload["gene"], clinvar="success", gnomad="success", vep="success", cache_hit=False)
        if calls["count"] == 2:
            return _result(case_id=payload["gene"], clinvar="no_record", gnomad="no_record", vep="partial", cache_hit=True)
        return _result(case_id=payload["gene"], clinvar="skipped", gnomad="failure", vep="failure", literature="skipped")

    result = run_provider_benchmark(case_runner=runner)

    assert result.dataset_size == 6
    assert result.clinvar.success == 1
    assert result.clinvar.no_record == 1
    assert result.clinvar.skipped == 4
    assert result.gnomad.failure == 4
    assert result.vep.partial == 1
    assert result.vep.failure == 4
    assert result.runtime["clinvar"].cache_hit_count == 1
    assert result.runtime["clinvar"].cache_miss_count == 1
    assert result.runtime["clinvar"].latency_scope == "provider"
    assert result.runtime["clinvar"].provider_latency_count == 2
    assert result.provider_yield["clinvar"].records_found == 1
    assert result.provider_yield["gnomad"].af_records_found == 1
    assert result.provider_yield["vep"].predictor_records_returned >= 2
    assert result.provider_yield["pubmed"].articles_found >= 2
    assert result.provider_yield["litvar"].citations_found >= 2

    report = render_provider_benchmark_report(result)
    assert "Dataset: 6 variants" in report
    assert "## Runtime" in report
    assert "scope=provider" in report
    assert "## Provider diagnostics" in report
    assert "gnomad error example" in report
    output = write_provider_benchmark_report(result, tmp_path / "provider_benchmark.md")
    assert output.exists()


def test_provider_benchmark_timeout_is_failure_not_crash() -> None:
    def runner(_payload: dict[str, Any]) -> dict[str, Any]:
        raise TimeoutError("provider timed out")

    result = run_provider_benchmark(case_runner=runner)

    assert result.dataset_size == 6
    assert result.clinvar.failure == 6
    assert result.gnomad.failure == 6
    assert result.vep.failure == 6
    assert result.runtime["clinvar"].timeout_count == 6
    assert result.runtime["clinvar"].latency_scope == "case"
    assert result.runtime["clinvar"].case_level_latency_used_count == 6
    assert result.limitations
    assert result.cases[0].status == "error"


def test_provider_benchmark_preserves_classification_as_observed_metric_only() -> None:
    result = run_provider_benchmark(case_runner=lambda payload: _result(case_id=payload["gene"]))

    assert all(case.classification_unchanged_by_benchmark for case in result.cases)
    assert result.summary["classification_benchmark"] is False
    assert "classification_result" not in result.model_dump(mode="json")


def test_provider_benchmark_marks_case_level_latency_when_provider_runtime_lacks_samples() -> None:
    result = run_provider_benchmark(
        case_runner=lambda payload: _result(case_id=payload["gene"], include_provider_latency=False)
    )

    assert result.runtime["clinvar"].latency_scope == "case"
    assert result.runtime["clinvar"].provider_latency_count == 0
    assert result.runtime["clinvar"].case_level_latency_used_count == 6
    report = render_provider_benchmark_report(result)
    assert "scope=case" in report
