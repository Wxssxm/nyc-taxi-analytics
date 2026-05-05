"""Benchmark identical analytical workloads across DuckDB, Polars, and Pandas.

The same logical computation is expressed in each engine's idiomatic API,
then timed. Results are rendered as a Markdown table and a matplotlib bar
chart saved to `docs/images/`.

The point is not to declare a winner but to show the order of magnitude:
DuckDB on Parquet is consistently fast because of vectorized execution and
Parquet pushdown; Polars is competitive thanks to its Rust engine; Pandas
is included because it's the baseline most data engineers know.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd
import polars as pl
from loguru import logger


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    workload: str
    engine: str
    elapsed_s: float
    rows: int


WORKLOADS: dict[str, str] = {
    "hourly_trip_count": "Trips grouped by hour of day",
    "top10_pickup_zones": "Top 10 pickup zones by trip count",
    "filter_long_trips_avg_fare": "Average fare for trips > 5 miles",
}


def _time(fn: Callable[[], pl.DataFrame | pd.DataFrame]) -> tuple[float, int]:
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    return elapsed, len(result)


def _duckdb_workloads(parquet_glob: str) -> dict[str, Callable[[], pl.DataFrame]]:
    con = duckdb.connect(":memory:")

    def hourly() -> pl.DataFrame:
        return con.execute(f"""
            SELECT EXTRACT(hour FROM tpep_pickup_datetime)::INT AS hour, COUNT(*) AS n
            FROM read_parquet('{parquet_glob}')
            GROUP BY hour ORDER BY hour
            """).pl()

    def top_zones() -> pl.DataFrame:
        return con.execute(f"""
            SELECT PULocationID, COUNT(*) AS n
            FROM read_parquet('{parquet_glob}')
            GROUP BY PULocationID ORDER BY n DESC LIMIT 10
            """).pl()

    def long_trips() -> pl.DataFrame:
        return con.execute(f"""
            SELECT AVG(fare_amount) AS avg_fare
            FROM read_parquet('{parquet_glob}')
            WHERE trip_distance > 5
            """).pl()

    return {
        "hourly_trip_count": hourly,
        "top10_pickup_zones": top_zones,
        "filter_long_trips_avg_fare": long_trips,
    }


def _polars_workloads(parquet_glob: str) -> dict[str, Callable[[], pl.DataFrame]]:
    def hourly() -> pl.DataFrame:
        return (
            pl.scan_parquet(parquet_glob)
            .with_columns(pl.col("tpep_pickup_datetime").dt.hour().alias("hour"))
            .group_by("hour")
            .agg(pl.len().alias("n"))
            .sort("hour")
            .collect()
        )

    def top_zones() -> pl.DataFrame:
        return (
            pl.scan_parquet(parquet_glob)
            .group_by("PULocationID")
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
            .head(10)
            .collect()
        )

    def long_trips() -> pl.DataFrame:
        return (
            pl.scan_parquet(parquet_glob)
            .filter(pl.col("trip_distance") > 5)
            .select(pl.col("fare_amount").mean().alias("avg_fare"))
            .collect()
        )

    return {
        "hourly_trip_count": hourly,
        "top10_pickup_zones": top_zones,
        "filter_long_trips_avg_fare": long_trips,
    }


def _pandas_workloads(parquet_files: list[Path]) -> dict[str, Callable[[], pd.DataFrame]]:
    def _read() -> pd.DataFrame:
        return pd.concat([pd.read_parquet(f) for f in parquet_files], ignore_index=True)

    def hourly() -> pd.DataFrame:
        df = _read()
        df["hour"] = df["tpep_pickup_datetime"].dt.hour
        return (
            df.groupby("hour", as_index=False)
            .size()
            .rename(columns={"size": "n"})
            .sort_values("hour")
        )

    def top_zones() -> pd.DataFrame:
        df = _read()
        return (
            df.groupby("PULocationID", as_index=False)
            .size()
            .rename(columns={"size": "n"})
            .sort_values("n", ascending=False)
            .head(10)
        )

    def long_trips() -> pd.DataFrame:
        df = _read()
        return pd.DataFrame({"avg_fare": [df.loc[df["trip_distance"] > 5, "fare_amount"].mean()]})

    return {
        "hourly_trip_count": hourly,
        "top10_pickup_zones": top_zones,
        "filter_long_trips_avg_fare": long_trips,
    }


def run_benchmarks(
    parquet_files: list[Path],
    repeats: int = 3,
) -> list[BenchmarkResult]:
    """Run all workloads on each engine `repeats` times, keep the fastest run."""
    if not parquet_files:
        raise ValueError("at least one parquet file required")

    glob = (
        str(parquet_files[0].parent / parquet_files[0].name)
        if len(parquet_files) == 1
        else str(
            parquet_files[0].parent / f"{parquet_files[0].name.split('_')[0]}_tripdata_*.parquet"
        )
    )

    engines: dict[str, dict[str, Callable]] = {
        "duckdb": _duckdb_workloads(glob),
        "polars": _polars_workloads(glob),
        "pandas": _pandas_workloads(parquet_files),
    }

    results: list[BenchmarkResult] = []
    for engine, workloads in engines.items():
        for name, fn in workloads.items():
            best_elapsed = float("inf")
            rows = 0
            for _ in range(repeats):
                elapsed, rows = _time(fn)
                best_elapsed = min(best_elapsed, elapsed)
            results.append(BenchmarkResult(name, engine, best_elapsed, rows))
            logger.info(
                "{engine:<7} {name:<32} {elapsed:.3f}s",
                engine=engine,
                name=name,
                elapsed=best_elapsed,
            )
    return results


def render_markdown(results: list[BenchmarkResult]) -> str:
    """Render results as a Markdown table grouped by workload."""
    by_workload: dict[str, dict[str, float]] = {}
    for r in results:
        by_workload.setdefault(r.workload, {})[r.engine] = r.elapsed_s

    lines = [
        "| Workload | DuckDB | Polars | Pandas | Speedup vs Pandas |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for workload, by_engine in by_workload.items():
        d = by_engine.get("duckdb", float("nan"))
        p = by_engine.get("polars", float("nan"))
        pd_ = by_engine.get("pandas", float("nan"))
        speedup = pd_ / d if d > 0 else 0
        lines.append(f"| `{workload}` | {d:.3f}s | {p:.3f}s | {pd_:.3f}s | {speedup:.1f}x |")
    return "\n".join(lines)


def render_chart(results: list[BenchmarkResult], out_path: Path) -> None:
    """Save a grouped bar chart of elapsed time per workload + engine."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    workloads = sorted({r.workload for r in results})
    engines = ["duckdb", "polars", "pandas"]

    matrix = [
        [
            next((r.elapsed_s for r in results if r.workload == w and r.engine == e), 0)
            for w in workloads
        ]
        for e in engines
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.25
    x = list(range(len(workloads)))
    colors = {"duckdb": "#FFCD00", "polars": "#1976D2", "pandas": "#388E3C"}
    for i, (engine, row) in enumerate(zip(engines, matrix, strict=True)):
        positions = [xi + (i - 1) * width for xi in x]
        ax.bar(positions, row, width, label=engine, color=colors[engine])

    ax.set_xticks(x)
    ax.set_xticklabels(workloads, rotation=15, ha="right")
    ax.set_ylabel("Time (seconds, lower is better)")
    ax.set_title("DuckDB vs Polars vs Pandas - elapsed time")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    logger.info("Chart saved to {}", out_path)
