"""Generate a small synthetic Yellow Taxi parquet sample for tests and CI.

The schema matches the real TLC 2024 parquet so all queries run against it
unchanged. Distributions are loose approximations of real data — good enough
for queries to return non-trivial results, not for actual analysis.

Run from repo root: `uv run python scripts/generate_sample_data.py`
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
N_ROWS = 10_000
SEED = 42


def main() -> None:
    rng = np.random.default_rng(SEED)
    random.seed(SEED)

    base_dt = datetime(2024, 1, 1)
    pickup_offsets_sec = rng.integers(0, 31 * 24 * 3600, size=N_ROWS)
    pickups = [base_dt + timedelta(seconds=int(s)) for s in pickup_offsets_sec]

    duration_min = rng.lognormal(mean=2.4, sigma=0.6, size=N_ROWS).clip(0.5, 180)
    dropoffs = [p + timedelta(minutes=float(d)) for p, d in zip(pickups, duration_min, strict=True)]

    distances = rng.lognormal(mean=0.8, sigma=0.7, size=N_ROWS).clip(0.0, 80.0).round(2)

    fare = (3.0 + 2.5 * distances + 0.3 * duration_min).round(2)
    tip_pct = np.where(rng.random(N_ROWS) < 0.65, rng.uniform(0.10, 0.30, N_ROWS), 0.0)
    tip = (fare * tip_pct).round(2)
    tolls = np.where(rng.random(N_ROWS) < 0.05, rng.uniform(2.0, 12.0, N_ROWS), 0.0).round(2)
    extra = rng.choice([0.0, 0.5, 1.0], size=N_ROWS, p=[0.6, 0.25, 0.15])
    mta_tax = np.full(N_ROWS, 0.5)
    improvement_surcharge = np.full(N_ROWS, 0.3)
    congestion = np.where(rng.random(N_ROWS) < 0.7, 2.5, 0.0)
    airport_fee = np.where(rng.random(N_ROWS) < 0.04, 1.75, 0.0)
    total = (
        fare + tip + tolls + extra + mta_tax + improvement_surcharge + congestion + airport_fee
    ).round(2)

    payment_type = rng.choice([1, 2, 3, 4], size=N_ROWS, p=[0.78, 0.18, 0.02, 0.02]).astype("int64")
    tip = np.where(payment_type == 2, 0.0, tip).round(2)
    total = (
        fare + tip + tolls + extra + mta_tax + improvement_surcharge + congestion + airport_fee
    ).round(2)

    passenger_count = rng.choice(
        [None, 1, 2, 3, 4, 5, 6], size=N_ROWS, p=[0.05, 0.65, 0.15, 0.07, 0.04, 0.02, 0.02]
    )
    passenger_count = np.where(
        passenger_count == None,  # noqa: E711
        np.nan,
        passenger_count.astype(float),
    )

    pu_locations = rng.integers(1, 266, size=N_ROWS).astype("int64")
    do_locations = rng.integers(1, 266, size=N_ROWS).astype("int64")

    # inject some "fraud" rows so q_fraud_heuristics returns hits
    n_fraud = 30
    fraud_idx = rng.choice(N_ROWS, size=n_fraud, replace=False)
    for i, idx in enumerate(fraud_idx):
        if i % 5 == 0:
            fare[idx] = -fare[idx]  # negative fare
            total[idx] = round(float(total[idx]) - 2 * float(fare[idx]), 2)
        elif i % 5 == 1:
            distances[idx] = 150.0  # too far
        elif i % 5 == 2:
            dropoffs[idx] = pickups[idx] + timedelta(hours=8)  # too long
        elif i % 5 == 3:
            dropoffs[idx] = pickups[idx] - timedelta(minutes=5)  # before pickup
        else:
            distances[idx] = 0.0
            fare[idx] = 25.0  # zero distance, real fare

    df = pl.DataFrame(
        {
            "VendorID": rng.choice([1, 2], size=N_ROWS).astype("int64"),
            "tpep_pickup_datetime": pickups,
            "tpep_dropoff_datetime": dropoffs,
            "passenger_count": passenger_count,
            "trip_distance": distances.astype("float64"),
            "RatecodeID": rng.choice(
                [1, 2, 3, 4, 5], size=N_ROWS, p=[0.9, 0.04, 0.02, 0.02, 0.02]
            ).astype("float64"),
            "store_and_fwd_flag": rng.choice(["N", "Y"], size=N_ROWS, p=[0.99, 0.01]),
            "PULocationID": pu_locations,
            "DOLocationID": do_locations,
            "payment_type": payment_type,
            "fare_amount": fare.astype("float64"),
            "extra": extra.astype("float64"),
            "mta_tax": mta_tax.astype("float64"),
            "tip_amount": tip.astype("float64"),
            "tolls_amount": tolls.astype("float64"),
            "improvement_surcharge": improvement_surcharge.astype("float64"),
            "total_amount": total.astype("float64"),
            "congestion_surcharge": congestion.astype("float64"),
            "Airport_fee": airport_fee.astype("float64"),
        }
    )

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SAMPLE_DIR / "yellow_tripdata_2024-01.parquet"
    df.write_parquet(out_path, compression="zstd")
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB, {N_ROWS} rows)")


if __name__ == "__main__":
    main()
