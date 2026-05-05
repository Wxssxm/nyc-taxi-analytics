"""Tests for nyc_taxi.benchmarks.compare."""

from __future__ import annotations

from pathlib import Path

import pytest

from nyc_taxi.benchmarks.compare import (
    WORKLOADS,
    BenchmarkResult,
    render_chart,
    render_markdown,
    run_benchmarks,
)


@pytest.fixture
def parquet_files(sample_dir: Path) -> list[Path]:
    files = sorted(sample_dir.glob("yellow_tripdata_*.parquet"))
    assert files, "sample parquet missing — run scripts/generate_sample_data.py"
    return files


def test_run_benchmarks_returns_one_per_engine_per_workload(parquet_files: list[Path]) -> None:
    results = run_benchmarks(parquet_files, repeats=1)
    expected = len(WORKLOADS) * 3  # 3 engines: duckdb, polars, pandas
    assert len(results) == expected

    engines = {r.engine for r in results}
    assert engines == {"duckdb", "polars", "pandas"}

    workloads = {r.workload for r in results}
    assert workloads == set(WORKLOADS.keys())


def test_run_benchmarks_raises_on_empty_files() -> None:
    with pytest.raises(ValueError, match="at least one parquet"):
        run_benchmarks([], repeats=1)


def test_render_markdown_includes_all_workloads() -> None:
    results = [
        BenchmarkResult("hourly_trip_count", "duckdb", 0.001, 24),
        BenchmarkResult("hourly_trip_count", "polars", 0.002, 24),
        BenchmarkResult("hourly_trip_count", "pandas", 0.005, 24),
    ]
    md = render_markdown(results)
    assert "hourly_trip_count" in md
    assert "DuckDB" in md and "Polars" in md and "Pandas" in md
    assert "5.0x" in md  # speedup column


def test_render_chart_writes_png(parquet_files: list[Path], tmp_path: Path) -> None:
    results = run_benchmarks(parquet_files, repeats=1)
    out = tmp_path / "chart.png"
    render_chart(results, out)
    assert out.exists()
    assert out.stat().st_size > 1000  # non-trivial PNG
