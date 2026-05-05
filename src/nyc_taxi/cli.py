"""Command-line interface for nyc-taxi-analytics."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from nyc_taxi.analytics.database import connect, register_views
from nyc_taxi.analytics.queries import ALL_QUERIES, run_all
from nyc_taxi.benchmarks.compare import (
    render_chart,
    render_markdown,
    run_benchmarks,
)
from nyc_taxi.config import get_settings
from nyc_taxi.ingestion.download import download_range

app = typer.Typer(
    name="nyc-taxi",
    help="High-performance SQL analytics on NYC TLC Yellow Taxi parquet files.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _df_to_rich_table(df: pl.DataFrame, title: str) -> Table:
    table = Table(title=title, show_lines=False)
    for col in df.columns:
        table.add_column(col)
    for row in df.iter_rows():
        table.add_row(*[str(v) if v is not None else "-" for v in row])
    return table


@app.command()
def download(
    start: Annotated[str | None, typer.Option(help="Start month YYYY-MM")] = None,
    end: Annotated[str | None, typer.Option(help="End month YYYY-MM")] = None,
    taxi_type: Annotated[str | None, typer.Option(help="yellow|green|fhv|fhvhv")] = None,
) -> None:
    """Download TLC parquet files for the configured month range."""
    settings = get_settings()
    types = [taxi_type] if taxi_type else settings.taxi_type_list
    download_range(
        taxi_types=types,
        start_month=start or settings.download_start_month,
        end_month=end or settings.download_end_month,
        data_dir=settings.data_dir,
        timeout=settings.http_timeout,
    )


@app.command(name="query")
def query(
    name: Annotated[
        str,
        typer.Argument(
            help=f"Query name. One of: {', '.join(ALL_QUERIES.keys())}, or 'all'.",
        ),
    ] = "all",
) -> None:
    """Run a single query (or 'all') and print results."""
    settings = get_settings()
    with connect(None) as con:
        register_views(con, settings.data_dir, settings.sample_dir, settings.taxi_type_list[0])

        if name == "all":
            for r in run_all(con):
                console.print(_df_to_rich_table(r.df, f"{r.name} - {r.description}"))
                console.print()
            return

        if name not in ALL_QUERIES:
            console.print(f"[red]Unknown query: {name}[/red]")
            console.print(f"Available: {', '.join(ALL_QUERIES.keys())}, or 'all'")
            raise typer.Exit(code=1)

        description, fn = ALL_QUERIES[name]
        df = fn(con)
        console.print(_df_to_rich_table(df, f"{name} - {description}"))


@app.command()
def benchmark(
    repeats: Annotated[int, typer.Option(min=1, max=20, help="Best-of-N runs")] = 3,
    chart_path: Annotated[
        Path | None,
        typer.Option(help="Where to save the bar chart"),
    ] = None,
) -> None:
    """Benchmark DuckDB vs Polars vs Pandas on identical workloads."""
    settings = get_settings()
    files = sorted(settings.data_dir.glob("yellow_tripdata_*.parquet"))
    if not files:
        files = sorted(settings.sample_dir.glob("yellow_tripdata_*.parquet"))
    if not files:
        console.print("[red]No parquet files found. Run `nyc-taxi download` first.[/red]")
        raise typer.Exit(code=1)

    results = run_benchmarks(files, repeats=repeats)
    console.print()
    console.print(render_markdown(results))
    out = chart_path or (Path(__file__).resolve().parents[2] / "docs" / "images" / "benchmark.png")
    render_chart(results, out)
    console.print(f"\nChart: [cyan]{out}[/cyan]")


@app.command()
def pipeline() -> None:
    """Run the full pipeline: download, query, benchmark."""
    logger.info("Starting full pipeline")
    download()
    query("all")
    benchmark()
    logger.success("Pipeline finished")


if __name__ == "__main__":
    app()
