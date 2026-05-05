"""Integration tests — full pipeline against the bundled sample."""

from __future__ import annotations

from pathlib import Path

import pytest

from nyc_taxi.analytics.database import connect, register_views
from nyc_taxi.analytics.queries import run_all
from nyc_taxi.benchmarks.compare import run_benchmarks


@pytest.mark.integration
def test_full_query_pipeline_against_sample(sample_dir: Path, tmp_path: Path) -> None:
    """Register views over sample parquet, run all 10 queries, verify shape."""
    empty_raw = tmp_path / "raw"
    empty_raw.mkdir()
    with connect(None) as con:
        n_files = register_views(con, empty_raw, sample_dir, "yellow")
        assert n_files >= 1
        results = run_all(con)
        assert len(results) == 10
        for r in results:
            assert len(r.df) >= 0
            assert len(r.df.columns) > 0


@pytest.mark.integration
def test_benchmark_pipeline_against_sample(sample_dir: Path) -> None:
    files = sorted(sample_dir.glob("yellow_tripdata_*.parquet"))
    results = run_benchmarks(files, repeats=1)
    by_workload: dict[str, list[float]] = {}
    for r in results:
        by_workload.setdefault(r.workload, []).append(r.elapsed_s)
    for workload, times in by_workload.items():
        assert len(times) == 3, f"missing engine for {workload}"
        assert all(t >= 0 for t in times)
