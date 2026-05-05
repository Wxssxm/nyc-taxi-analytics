# Architecture

> Detailed architecture documentation. See the root `README.md` for the high-level diagram and quickstart.

## Why DuckDB?

NYC TLC publishes monthly trip records as Parquet — a columnar, compressed format already optimized for analytics. DuckDB can query Parquet files directly without ingestion: no warehouse to provision, no ETL to run before the first query.

For a portfolio-sized dataset (a few months of yellow taxi trips, ~30M rows / ~1 GB compressed), DuckDB on a single machine outperforms much heavier setups.

## Components

```
┌────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│  TLC CDN           │───▶│  Ingestion           │───▶│  data/raw/*.parquet │
│  (parquet/month)   │    │  httpx + tenacity    │    │  (one file/month)   │
└────────────────────┘    └──────────────────────┘    └──────────┬──────────┘
                                                                  │
                                                                  ▼
                          ┌──────────────────────┐    ┌─────────────────────┐
                          │  DuckDB views        │◀───│  Glob over parquet  │
                          │  (zero-copy)         │    │  data/raw/*.parquet │
                          └──────────┬───────────┘    └─────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  Analytics queries   │
                          │  (10 SQL functions)  │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  Benchmarks          │
                          │  DuckDB vs Pandas    │
                          │  vs Polars           │
                          └──────────────────────┘
```

## Data flow

1. **Download** (`ingestion/download.py`) — pulls monthly Parquet files from the TLC CDN. Idempotent: existing files of the right size are skipped.
2. **Register** (`analytics/queries.py`) — DuckDB views are created over a Parquet glob; no copy, no insert.
3. **Query** — analytics functions return Polars or Pandas DataFrames depending on the call site.
4. **Benchmark** (`benchmarks/compare.py`) — same logical query is executed on each engine, timed, and rendered as a Markdown table + chart.

## Why no orchestrator?

This project deliberately omits Airflow/Prefect/Dagster. The point is to demonstrate that for many real analytics workloads, a few well-chosen Parquet files plus DuckDB is the entire pipeline. Orchestration is an answer to scale; this project is an answer to "how much can you do without it?"
