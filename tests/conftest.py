"""Pytest fixtures shared across tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from nyc_taxi.analytics.database import register_views

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "data" / "sample"


@pytest.fixture(scope="session")
def sample_dir() -> Path:
    return SAMPLE_DIR


@pytest.fixture(scope="session")
def empty_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An empty data dir, so register_views falls back to the sample dir."""
    return tmp_path_factory.mktemp("empty_raw")


@pytest.fixture
def duckdb_con(sample_dir: Path, empty_data_dir: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB with views registered against the sample parquet."""
    con = duckdb.connect(":memory:")
    register_views(con, empty_data_dir, sample_dir, taxi_type="yellow")
    try:
        yield con
    finally:
        con.close()
