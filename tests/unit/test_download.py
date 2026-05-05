"""Tests for nyc_taxi.ingestion.download."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from nyc_taxi.ingestion.download import (
    TLC_BASE_URL,
    build_url,
    download_one,
    download_range,
    iter_months,
)

FAKE_PARQUET_BYTES = b"PAR1" + b"\0" * 1024 + b"PAR1"  # not real parquet, fine for testing the IO layer


def test_iter_months_simple() -> None:
    assert list(iter_months("2024-01", "2024-03")) == ["2024-01", "2024-02", "2024-03"]


def test_iter_months_year_boundary() -> None:
    assert list(iter_months("2023-11", "2024-02")) == ["2023-11", "2023-12", "2024-01", "2024-02"]


def test_iter_months_single_month() -> None:
    assert list(iter_months("2024-06", "2024-06")) == ["2024-06"]


def test_iter_months_inverted_range_raises() -> None:
    with pytest.raises(ValueError, match="after end"):
        list(iter_months("2024-06", "2024-01"))


def test_build_url_yellow() -> None:
    assert build_url("yellow", "2024-01") == f"{TLC_BASE_URL}/yellow_tripdata_2024-01.parquet"


def test_build_url_invalid_taxi_type() -> None:
    with pytest.raises(ValueError, match="taxi_type"):
        build_url("blue", "2024-01")


def test_build_url_invalid_month() -> None:
    with pytest.raises(ValueError, match="YYYY-MM"):
        build_url("yellow", "2024-13")


@respx.mock
def test_download_one_writes_file(tmp_path: Path) -> None:
    url = build_url("yellow", "2024-01")
    respx.head(url).mock(return_value=httpx.Response(200, headers={"content-length": str(len(FAKE_PARQUET_BYTES))}))
    respx.get(url).mock(return_value=httpx.Response(200, content=FAKE_PARQUET_BYTES))

    result = download_one("yellow", "2024-01", tmp_path, timeout=30)

    assert result.path.exists()
    assert result.path.read_bytes() == FAKE_PARQUET_BYTES
    assert result.bytes_downloaded == len(FAKE_PARQUET_BYTES)
    assert result.skipped is False


@respx.mock
def test_download_one_skips_when_size_matches(tmp_path: Path) -> None:
    url = build_url("yellow", "2024-01")
    dest = tmp_path / "yellow_tripdata_2024-01.parquet"
    dest.write_bytes(FAKE_PARQUET_BYTES)

    respx.head(url).mock(return_value=httpx.Response(200, headers={"content-length": str(len(FAKE_PARQUET_BYTES))}))

    result = download_one("yellow", "2024-01", tmp_path, timeout=30)

    assert result.skipped is True
    assert result.bytes_downloaded == len(FAKE_PARQUET_BYTES)


@respx.mock
def test_download_one_redownloads_on_size_mismatch(tmp_path: Path) -> None:
    url = build_url("yellow", "2024-01")
    dest = tmp_path / "yellow_tripdata_2024-01.parquet"
    dest.write_bytes(b"stale")  # smaller than remote

    respx.head(url).mock(return_value=httpx.Response(200, headers={"content-length": str(len(FAKE_PARQUET_BYTES))}))
    respx.get(url).mock(return_value=httpx.Response(200, content=FAKE_PARQUET_BYTES))

    result = download_one("yellow", "2024-01", tmp_path, timeout=30)

    assert result.skipped is False
    assert dest.read_bytes() == FAKE_PARQUET_BYTES


@respx.mock
def test_download_one_retries_on_500(tmp_path: Path) -> None:
    url = build_url("yellow", "2024-01")
    respx.head(url).mock(return_value=httpx.Response(200, headers={"content-length": str(len(FAKE_PARQUET_BYTES))}))
    route = respx.get(url).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, content=FAKE_PARQUET_BYTES),
        ]
    )

    result = download_one("yellow", "2024-01", tmp_path, timeout=30)

    assert route.call_count == 2
    assert result.bytes_downloaded == len(FAKE_PARQUET_BYTES)


@respx.mock
def test_download_range_handles_failure_per_file(tmp_path: Path) -> None:
    """A single failing month doesn't abort the whole run."""
    url_jan = build_url("yellow", "2024-01")
    url_feb = build_url("yellow", "2024-02")

    respx.head(url_jan).mock(return_value=httpx.Response(200, headers={"content-length": str(len(FAKE_PARQUET_BYTES))}))
    respx.get(url_jan).mock(return_value=httpx.Response(200, content=FAKE_PARQUET_BYTES))

    respx.head(url_feb).mock(return_value=httpx.Response(404))
    respx.get(url_feb).mock(return_value=httpx.Response(404))

    results = download_range(["yellow"], "2024-01", "2024-02", tmp_path, timeout=30)

    assert len(results) == 1
    assert results[0].month == "2024-01"
