"""Download NYC TLC trip data parquet files from the public CDN.

The TLC publishes one parquet file per (taxi type, month). Files are typically
10-60 MB compressed. This module downloads them idempotently: if a local file
exists with the same Content-Length as the remote, the download is skipped.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
from loguru import logger
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
"""TLC public CDN base URL — see https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page"""

VALID_TAXI_TYPES: frozenset[str] = frozenset({"yellow", "green", "fhv", "fhvhv"})


@dataclass(frozen=True, slots=True)
class DownloadResult:
    taxi_type: str
    month: str
    path: Path
    bytes_downloaded: int
    skipped: bool


def iter_months(start: str, end: str) -> Iterator[str]:
    """Yield months in YYYY-MM format, inclusive on both ends."""
    s_year, s_month = (int(x) for x in start.split("-"))
    e_year, e_month = (int(x) for x in end.split("-"))
    if (s_year, s_month) > (e_year, e_month):
        raise ValueError(f"start {start!r} is after end {end!r}")

    year, month = s_year, s_month
    while (year, month) <= (e_year, e_month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month > 12:
            month = 1
            year += 1


def build_url(taxi_type: str, month: str) -> str:
    """Return the parquet URL for a given taxi type and YYYY-MM month."""
    if taxi_type not in VALID_TAXI_TYPES:
        raise ValueError(f"taxi_type must be one of {sorted(VALID_TAXI_TYPES)}, got {taxi_type!r}")
    try:
        year, mon = month.split("-")
        date(int(year), int(mon), 1)
    except (ValueError, AttributeError) as e:
        raise ValueError(f"month must be YYYY-MM, got {month!r}") from e
    return f"{TLC_BASE_URL}/{taxi_type}_tripdata_{month}.parquet"


def _log_retry(retry_state: RetryCallState) -> None:
    if retry_state.outcome and retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        logger.warning(
            "Download attempt {attempt} failed: {exc}; retrying...",
            attempt=retry_state.attempt_number,
            exc=exc,
        )


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    before_sleep=_log_retry,
    reraise=True,
)
def _stream_to_disk(url: str, dest: Path, timeout: int) -> int:
    """Stream a URL to a destination path. Returns bytes written."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    bytes_written = 0
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
        response.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
                bytes_written += len(chunk)
    tmp.replace(dest)
    return bytes_written


def _remote_size(url: str, timeout: int) -> int | None:
    """Return the remote Content-Length, or None if unavailable."""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.head(url, follow_redirects=True)
            r.raise_for_status()
            cl = r.headers.get("content-length")
            return int(cl) if cl else None
    except httpx.HTTPError as e:
        logger.warning("HEAD request failed for {url}: {exc}", url=url, exc=e)
        return None


def download_one(
    taxi_type: str,
    month: str,
    data_dir: Path,
    timeout: int = 300,
) -> DownloadResult:
    """Download a single (taxi_type, month) parquet file. Idempotent."""
    url = build_url(taxi_type, month)
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / f"{taxi_type}_tripdata_{month}.parquet"

    if dest.exists():
        local_size = dest.stat().st_size
        remote_size = _remote_size(url, timeout)
        if remote_size is not None and local_size == remote_size:
            logger.info(
                "Skipping {file} — already downloaded ({size:.1f} MB)",
                file=dest.name,
                size=local_size / 1e6,
            )
            return DownloadResult(taxi_type, month, dest, local_size, skipped=True)
        logger.info(
            "Re-downloading {file} (local {local} vs remote {remote})",
            file=dest.name,
            local=local_size,
            remote=remote_size,
        )

    logger.info("Downloading {url}", url=url)
    bytes_written = _stream_to_disk(url, dest, timeout)
    logger.success("Downloaded {file} ({size:.1f} MB)", file=dest.name, size=bytes_written / 1e6)
    return DownloadResult(taxi_type, month, dest, bytes_written, skipped=False)


def download_range(
    taxi_types: list[str],
    start_month: str,
    end_month: str,
    data_dir: Path,
    timeout: int = 300,
) -> list[DownloadResult]:
    """Download all combinations of taxi_types and the month range.

    Failures on individual files are logged and skipped, so a single bad month
    doesn't abort the whole run.
    """
    results: list[DownloadResult] = []
    months = list(iter_months(start_month, end_month))
    total = len(months) * len(taxi_types)
    logger.info(
        "Downloading {n} files: types={types} months={start}..{end}",
        n=total,
        types=taxi_types,
        start=start_month,
        end=end_month,
    )

    for taxi_type in taxi_types:
        for month in months:
            try:
                results.append(download_one(taxi_type, month, data_dir, timeout))
            except httpx.HTTPError as e:
                logger.error(
                    "Failed to download {type} {month}: {exc}", type=taxi_type, month=month, exc=e
                )

    skipped = sum(1 for r in results if r.skipped)
    downloaded = len(results) - skipped
    total_mb = sum(r.bytes_downloaded for r in results if not r.skipped) / 1e6
    logger.success(
        "Done: {dl} downloaded ({mb:.1f} MB), {sk} skipped, {fail} failed",
        dl=downloaded,
        mb=total_mb,
        sk=skipped,
        fail=total - len(results),
    )
    return results
