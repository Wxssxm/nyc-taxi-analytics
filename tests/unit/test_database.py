"""Tests for nyc_taxi.analytics.database."""

from __future__ import annotations

from pathlib import Path

import pytest

from nyc_taxi.analytics.database import connect, find_parquet_files, register_views


def test_find_parquet_files_returns_sample_when_data_empty(
    tmp_path: Path, sample_dir: Path
) -> None:
    files = find_parquet_files(tmp_path, sample_dir, "yellow")
    assert len(files) >= 1
    assert all(f.name.startswith("yellow_tripdata_") for f in files)


def test_find_parquet_files_returns_empty_when_both_empty(tmp_path: Path) -> None:
    other_empty = tmp_path / "other"
    other_empty.mkdir()
    assert find_parquet_files(tmp_path, other_empty, "yellow") == []


def test_register_views_creates_expected_views(sample_dir: Path, tmp_path: Path) -> None:
    with connect(None) as con:
        register_views(con, tmp_path, sample_dir, "yellow")
        view_names = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        assert {"trips", "taxi_zones", "payment_types"} <= view_names


def test_register_views_raises_when_no_files(tmp_path: Path) -> None:
    other_empty = tmp_path / "other"
    other_empty.mkdir()
    with connect(None) as con, pytest.raises(FileNotFoundError, match="No parquet files"):
        register_views(con, tmp_path, other_empty, "yellow")


def test_connect_persists_to_disk(tmp_path: Path) -> None:
    db_path = tmp_path / "scratch.duckdb"
    with connect(db_path) as con:
        con.execute("CREATE TABLE t (a INT)").execute("INSERT INTO t VALUES (1), (2)")
    assert db_path.exists()

    with connect(db_path, read_only=True) as con:
        rows = con.execute("SELECT a FROM t ORDER BY a").fetchall()
        assert rows == [(1,), (2,)]
