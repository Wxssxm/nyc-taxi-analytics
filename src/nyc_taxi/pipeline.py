"""End-to-end pipeline entry point: `python -m nyc_taxi.pipeline`.

Runs download -> queries -> benchmark sequentially. Convenience wrapper around
the CLI's `pipeline` command, useful when you don't want to install the package
as a script (e.g., inside Docker or quick scripting).
"""

from __future__ import annotations

from loguru import logger

from nyc_taxi.analytics.database import connect, register_views
from nyc_taxi.analytics.queries import run_all
from nyc_taxi.benchmarks.compare import render_chart, render_markdown, run_benchmarks
from nyc_taxi.config import get_settings
from nyc_taxi.ingestion.download import download_range


def main() -> None:
    settings = get_settings()
    logger.info("=== Step 1/3: download ===")
    download_range(
        taxi_types=settings.taxi_type_list,
        start_month=settings.download_start_month,
        end_month=settings.download_end_month,
        data_dir=settings.data_dir,
        timeout=settings.http_timeout,
    )

    logger.info("=== Step 2/3: queries ===")
    with connect(None) as con:
        register_views(con, settings.data_dir, settings.sample_dir, settings.taxi_type_list[0])
        for r in run_all(con):
            logger.info("Query {} returned {} rows", r.name, len(r.df))

    logger.info("=== Step 3/3: benchmarks ===")
    files = sorted(settings.data_dir.glob("yellow_tripdata_*.parquet"))
    if not files:
        files = sorted(settings.sample_dir.glob("yellow_tripdata_*.parquet"))
    if files:
        results = run_benchmarks(files, repeats=3)
        logger.info("\n{}", render_markdown(results))
        chart_path = settings.data_dir.parent.parent / "docs" / "images" / "benchmark.png"
        render_chart(results, chart_path)
    else:
        logger.warning("No parquet files for benchmarks; skipping")

    logger.success("Pipeline complete")


if __name__ == "__main__":
    main()
