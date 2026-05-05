"""Tests for nyc_taxi.analytics.queries — run every query against sample data."""

from __future__ import annotations

import duckdb
import pytest

from nyc_taxi.analytics.queries import (
    ALL_QUERIES,
    q_avg_fare_per_mile_by_hour,
    q_daily_volume_trend,
    q_fraud_heuristics,
    q_hourly_revenue,
    q_passenger_distribution,
    q_tip_patterns_by_payment,
    q_top_pickup_zones,
    q_top_routes,
    q_trip_duration_percentiles,
    q_weekend_vs_weekday,
    run_all,
)


def test_top_pickup_zones_returns_n_rows(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_top_pickup_zones(duckdb_con, limit=5)
    assert len(df) <= 5
    assert {"borough", "zone", "trip_count", "avg_fare_usd", "total_revenue_usd"} <= set(df.columns)
    assert df["trip_count"].sum() > 0


def test_hourly_revenue_has_24_or_fewer_hours(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_hourly_revenue(duckdb_con)
    assert 1 <= len(df) <= 24
    assert df["hour_of_day"].min() >= 0
    assert df["hour_of_day"].max() <= 23


def test_tip_patterns_returns_known_payment_types(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_tip_patterns_by_payment(duckdb_con)
    labels = set(df["payment_label"].to_list())
    assert labels & {"Credit card", "Cash"}


def test_duration_percentiles_are_monotonic(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_trip_duration_percentiles(duckdb_con)
    row = df.row(0, named=True)
    assert row["p50_min"] <= row["p75_min"] <= row["p90_min"] <= row["p99_min"]
    assert row["trip_count"] > 0


def test_avg_fare_per_mile_returns_positive_values(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_avg_fare_per_mile_by_hour(duckdb_con)
    assert (df["usd_per_mile"] > 0).all()


def test_weekend_vs_weekday_has_two_rows(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_weekend_vs_weekday(duckdb_con)
    assert sorted(df["day_type"].to_list()) == ["weekday", "weekend"]


def test_fraud_heuristics_returns_known_flags(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_fraud_heuristics(duckdb_con)
    flags = set(df["flag"].to_list())
    assert {
        "negative_fare",
        "distance_over_100mi",
        "duration_over_6h",
        "pickup_after_dropoff",
        "zero_distance_with_fare",
        "tip_over_50pct",
    } == flags
    assert (df["hits"] >= 0).all()


def test_top_routes_respects_limit(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_top_routes(duckdb_con, limit=3)
    assert len(df) <= 3
    assert "pickup_zone" in df.columns and "dropoff_zone" in df.columns


def test_daily_volume_is_sorted(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_daily_volume_trend(duckdb_con)
    dates = df["pickup_date"].to_list()
    assert dates == sorted(dates)


def test_passenger_distribution_pct_sums_to_100(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    df = q_passenger_distribution(duckdb_con)
    assert df["pct_of_total"].sum() == pytest.approx(100.0, abs=0.5)


def test_run_all_returns_one_per_query(duckdb_con: duckdb.DuckDBPyConnection) -> None:
    results = run_all(duckdb_con)
    assert len(results) == len(ALL_QUERIES)
    assert {r.name for r in results} == set(ALL_QUERIES.keys())
    for r in results:
        assert len(r.df) >= 0
