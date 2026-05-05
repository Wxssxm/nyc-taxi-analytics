"""DuckDB connection management and view registration.

Views are created over the Parquet glob (zero-copy). If `data/raw/` is empty,
the sample data in `data/sample/` is used as a fallback so that queries always
have something to work against.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
from loguru import logger


def find_parquet_files(data_dir: Path, sample_dir: Path, taxi_type: str = "yellow") -> list[Path]:
    """Return parquet files in data_dir, falling back to sample_dir if empty."""
    pattern = f"{taxi_type}_tripdata_*.parquet"
    files = sorted(data_dir.glob(pattern)) if data_dir.exists() else []
    if files:
        return files
    if sample_dir.exists():
        sample_files = sorted(sample_dir.glob(pattern))
        if sample_files:
            logger.info("No files in {}; using {} sample(s)", data_dir, len(sample_files))
            return sample_files
    return []


@contextmanager
def connect(
    duckdb_path: Path | None = None, read_only: bool = False
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Context-managed DuckDB connection. Pass None for in-memory."""
    target = ":memory:" if duckdb_path is None else str(duckdb_path)
    if duckdb_path is not None:
        duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(target, read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def register_views(
    con: duckdb.DuckDBPyConnection,
    data_dir: Path,
    sample_dir: Path,
    taxi_type: str = "yellow",
) -> int:
    """Register `trips` and `taxi_zones` views. Returns the number of parquet files attached."""
    files = find_parquet_files(data_dir, sample_dir, taxi_type)
    if not files:
        raise FileNotFoundError(
            f"No parquet files found in {data_dir} or {sample_dir} for {taxi_type!r}. "
            "Run `nyc-taxi download` first."
        )

    file_list_sql = ", ".join(f"'{f}'" for f in files)
    con.execute(f"""
        CREATE OR REPLACE VIEW trips AS
        SELECT * FROM read_parquet([{file_list_sql}], union_by_name=true)
        """)

    zones_csv = sample_dir / "taxi_zones.csv"
    if zones_csv.exists():
        con.execute(f"""
            CREATE OR REPLACE VIEW taxi_zones AS
            SELECT
                LocationID AS location_id,
                Borough AS borough,
                Zone AS zone,
                service_zone
            FROM read_csv_auto('{zones_csv}', header=true)
            """)
    else:
        logger.warning("taxi_zones.csv not found at {}; zone joins will fail", zones_csv)

    con.execute("""
        CREATE OR REPLACE VIEW payment_types AS
        SELECT * FROM (VALUES
            (1, 'Credit card'),
            (2, 'Cash'),
            (3, 'No charge'),
            (4, 'Dispute'),
            (5, 'Unknown'),
            (6, 'Voided trip')
        ) AS t(payment_type, payment_label)
        """)

    logger.info("Registered views: trips ({} file(s)), taxi_zones, payment_types", len(files))
    return len(files)
