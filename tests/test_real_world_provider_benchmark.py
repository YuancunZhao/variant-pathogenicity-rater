from __future__ import annotations

import os
import json
from pathlib import Path

import pytest

from variant_pathogenicity_rater.benchmark.provider_benchmark import (
    render_provider_benchmark_report,
    run_provider_benchmark,
    write_provider_benchmark_report,
)


def test_real_world_provider_benchmark_is_env_gated(tmp_path: Path) -> None:
    if os.environ.get("VPR_RUN_PROVIDER_BENCHMARK") != "1":
        pytest.skip("Real-world provider benchmark is opt-in; set VPR_RUN_PROVIDER_BENCHMARK=1.")

    result = run_provider_benchmark(
        use_online=True,
        include_litvar=os.environ.get("VPR_RUN_PROVIDER_BENCHMARK_LITVAR") == "1",
        provider_cache_dir=str(tmp_path / "provider-benchmark-cache"),
        provider_timeout=float(os.environ.get("VPR_PROVIDER_BENCHMARK_TIMEOUT", "10")),
    )
    report = render_provider_benchmark_report(result)
    output_dir = os.environ.get("VPR_PROVIDER_BENCHMARK_OUTPUT_DIR")
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        write_provider_benchmark_report(result, output_path / "provider_benchmark_report.md")
        (output_path / "provider_benchmark_result.json").write_text(
            result.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    assert result.dataset_size == 6
    assert result.cases
    assert "Dataset: 6 variants" in report
    if output_dir:
        parsed = json.loads((Path(output_dir) / "provider_benchmark_result.json").read_text())
        assert parsed["dataset_size"] == 6
        assert "clinvar" in (Path(output_dir) / "provider_benchmark_report.md").read_text()
    for case in result.cases:
        assert case.status in {"ok", "error"}
        assert case.provider_runtime
