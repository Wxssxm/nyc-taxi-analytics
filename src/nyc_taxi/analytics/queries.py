"""Ten analytical SQL queries over the `trips` view (registered by `database.py`).

Each query takes a connected, view-registered DuckDB connection and returns a
Polars DataFrame. Queries are designed to be expressive in SQL — the Python
wrapper exists only to give them names and parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import polars as pl


@dataclass(frozen=True, slots=True)
class QueryResult:
    name: str
    description: str
    df: pl.DataFrame


def _run(con: duckdb.DuckDBPyConnection, sql: str) -> pl.DataFrame:
    return con.execute(sql).pl()


def q_top_pickup_zones(con: duckdb.DuckDBPyConnection, limit: int = 10) -> pl.DataFrame:
    """Top N pickup zones by trip count, with revenue."""
    return _run(
        con,
        f"""
        SELECT
            z.borough,
            z.zone,
            COUNT(*) AS trip_count,
            ROUND(AVG(t.total_amount), 2) AS avg_fare_usd,
            ROUND(SUM(t.total_amount), 0) AS total_revenue_usd
        FROM trips t
        LEFT JOIN taxi_zones z ON t.PULocationID = z.location_id
        WHERE t.total_amount > 0
        GROUP BY z.borough, z.zone
        ORDER BY trip_count DESC
        LIMIT {limit}
        """,
    )


def q_hourly_revenue(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Trip volume and revenue by hour of day."""
    return _run(
        con,
        """
        SELECT
            EXTRACT(hour FROM tpep_pickup_datetime)::INT AS hour_of_day,
            COUNT(*) AS trips,
            ROUND(SUM(total_amount), 0) AS revenue_usd,
            ROUND(AVG(total_amount), 2) AS avg_fare_usd
        FROM trips
        WHERE total_amount > 0
        GROUP BY hour_of_day
        ORDER BY hour_of_day
        """,
    )


def q_tip_patterns_by_payment(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Average tip percentage by payment method (credit cards tip; cash trips report $0)."""
    return _run(
        con,
        """
        SELECT
            p.payment_label,
            COUNT(*) AS trip_count,
            ROUND(AVG(t.tip_amount), 2) AS avg_tip_usd,
            ROUND(AVG(CASE WHEN t.fare_amount > 0
                           THEN 100.0 * t.tip_amount / t.fare_amount END), 2) AS avg_tip_pct
        FROM trips t
        LEFT JOIN payment_types p ON t.payment_type = p.payment_type
        WHERE t.fare_amount > 0
        GROUP BY p.payment_label
        ORDER BY trip_count DESC
        """,
    )


def q_trip_duration_percentiles(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Trip duration percentiles (minutes), filtered to plausible trips."""
    return _run(
        con,
        """
        WITH durations AS (
            SELECT EXTRACT(epoch FROM tpep_dropoff_datetime - tpep_pickup_datetime) / 60.0 AS minutes
            FROM trips
            WHERE tpep_dropoff_datetime > tpep_pickup_datetime
        )
        SELECT
            ROUND(QUANTILE_CONT(minutes, 0.50), 1) AS p50_min,
            ROUND(QUANTILE_CONT(minutes, 0.75), 1) AS p75_min,
            ROUND(QUANTILE_CONT(minutes, 0.90), 1) AS p90_min,
            ROUND(QUANTILE_CONT(minutes, 0.99), 1) AS p99_min,
            ROUND(AVG(minutes), 1) AS avg_min,
            COUNT(*) AS trip_count
        FROM durations
        WHERE minutes BETWEEN 0 AND 360
        """,
    )


def q_avg_fare_per_mile_by_hour(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Average $/mile by pickup hour — efficiency proxy."""
    return _run(
        con,
        """
        SELECT
            EXTRACT(hour FROM tpep_pickup_datetime)::INT AS hour_of_day,
            ROUND(AVG(fare_amount / NULLIF(trip_distance, 0)), 2) AS usd_per_mile,
            ROUND(AVG(trip_distance), 2) AS avg_distance_mi
        FROM trips
        WHERE trip_distance > 0.1 AND fare_amount > 0
        GROUP BY hour_of_day
        ORDER BY hour_of_day
        """,
    )


def q_weekend_vs_weekday(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Trip volume, fare, and tip comparison: weekday vs weekend."""
    return _run(
        con,
        """
        SELECT
            CASE WHEN EXTRACT(dow FROM tpep_pickup_datetime) IN (0, 6)
                 THEN 'weekend' ELSE 'weekday' END AS day_type,
            COUNT(*) AS trips,
            ROUND(AVG(total_amount), 2) AS avg_fare_usd,
            ROUND(AVG(tip_amount), 2) AS avg_tip_usd,
            ROUND(AVG(trip_distance), 2) AS avg_distance_mi
        FROM trips
        WHERE total_amount > 0
        GROUP BY day_type
        ORDER BY day_type
        """,
    )


def q_fraud_heuristics(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Heuristic flags for suspicious trips (negative fares, > 100 mi, > 6h, etc.)."""
    return _run(
        con,
        """
        SELECT
            'negative_fare' AS flag, COUNT(*) AS hits FROM trips WHERE fare_amount < 0
        UNION ALL SELECT 'distance_over_100mi', COUNT(*) FROM trips WHERE trip_distance > 100
        UNION ALL SELECT 'duration_over_6h', COUNT(*) FROM trips
            WHERE EXTRACT(epoch FROM tpep_dropoff_datetime - tpep_pickup_datetime) > 21600
        UNION ALL SELECT 'pickup_after_dropoff', COUNT(*) FROM trips
            WHERE tpep_dropoff_datetime < tpep_pickup_datetime
        UNION ALL SELECT 'zero_distance_with_fare', COUNT(*) FROM trips
            WHERE trip_distance = 0 AND fare_amount > 5
        UNION ALL SELECT 'tip_over_50pct', COUNT(*) FROM trips
            WHERE fare_amount > 0 AND tip_amount / fare_amount > 0.5
        ORDER BY hits DESC
        """,
    )


def q_top_routes(con: duckdb.DuckDBPyConnection, limit: int = 10) -> pl.DataFrame:
    """Top N (pickup zone -> dropoff zone) routes by trip count."""
    return _run(
        con,
        f"""
        SELECT
            zp.zone AS pickup_zone,
            zd.zone AS dropoff_zone,
            COUNT(*) AS trip_count,
            ROUND(AVG(t.total_amount), 2) AS avg_fare_usd,
            ROUND(AVG(t.trip_distance), 2) AS avg_distance_mi
        FROM trips t
        LEFT JOIN taxi_zones zp ON t.PULocationID = zp.location_id
        LEFT JOIN taxi_zones zd ON t.DOLocationID = zd.location_id
        WHERE zp.zone IS NOT NULL AND zd.zone IS NOT NULL
        GROUP BY pickup_zone, dropoff_zone
        ORDER BY trip_count DESC
        LIMIT {limit}
        """,
    )


def q_daily_volume_trend(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Daily trip count and revenue."""
    return _run(
        con,
        """
        SELECT
            DATE_TRUNC('day', tpep_pickup_datetime)::DATE AS pickup_date,
            COUNT(*) AS trips,
            ROUND(SUM(total_amount), 0) AS revenue_usd
        FROM trips
        WHERE total_amount > 0
        GROUP BY pickup_date
        ORDER BY pickup_date
        """,
    )


def q_passenger_distribution(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    """Distribution of passenger count per trip.

    `passenger_count` is DOUBLE in TLC parquet (nulls + occasional NaN), so we
    use TRY_CAST inside COALESCE to map both to 0.
    """
    return _run(
        con,
        """
        SELECT
            COALESCE(TRY_CAST(passenger_count AS INTEGER), 0) AS passengers,
            COUNT(*) AS trips,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
            ROUND(AVG(total_amount), 2) AS avg_fare_usd
        FROM trips
        GROUP BY passengers
        ORDER BY passengers
        """,
    )


ALL_QUERIES: dict[str, tuple[str, callable]] = {
    "top-zones": ("Top pickup zones by trip count", q_top_pickup_zones),
    "hourly-revenue": ("Hourly trip volume and revenue", q_hourly_revenue),
    "tip-patterns": ("Tip patterns by payment method", q_tip_patterns_by_payment),
    "duration-percentiles": ("Trip duration percentiles (minutes)", q_trip_duration_percentiles),
    "fare-per-mile": ("Average fare per mile by hour", q_avg_fare_per_mile_by_hour),
    "weekend-vs-weekday": ("Weekday vs weekend comparison", q_weekend_vs_weekday),
    "fraud-heuristics": ("Suspicious trip indicators", q_fraud_heuristics),
    "top-routes": ("Top pickup -> dropoff routes", q_top_routes),
    "daily-trend": ("Daily volume and revenue", q_daily_volume_trend),
    "passenger-distribution": ("Passenger count distribution", q_passenger_distribution),
}


def run_all(con: duckdb.DuckDBPyConnection) -> list[QueryResult]:
    """Run every query in ALL_QUERIES, returning labeled results."""
    out: list[QueryResult] = []
    for name, (description, fn) in ALL_QUERIES.items():
        out.append(QueryResult(name=name, description=description, df=fn(con)))
    return out
