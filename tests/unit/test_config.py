"""Tests for nyc_taxi.config."""

from __future__ import annotations

import pytest

from nyc_taxi.config import Settings


def test_defaults_load() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.download_start_month == "2024-01"
    assert s.download_end_month == "2024-03"
    assert s.taxi_type_list == ["yellow"]
    assert s.http_timeout == 300


def test_taxi_type_list_parses_csv() -> None:
    s = Settings(_env_file=None, taxi_types="yellow,green, fhv")  # type: ignore[call-arg]
    assert s.taxi_type_list == ["yellow", "green", "fhv"]


@pytest.mark.parametrize("bad_month", ["2024", "2024-13", "abc-01", "2024/01"])
def test_invalid_month_rejected(bad_month: str) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, download_start_month=bad_month)  # type: ignore[call-arg]


def test_http_timeout_bounds() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, http_timeout=5)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        Settings(_env_file=None, http_timeout=10_000)  # type: ignore[call-arg]
