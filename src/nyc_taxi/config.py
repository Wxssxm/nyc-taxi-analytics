"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    data_dir: Path = Field(default=PROJECT_ROOT / "data" / "raw")
    duckdb_path: Path = Field(default=PROJECT_ROOT / "data" / "nyc_taxi.duckdb")
    sample_dir: Path = Field(default=PROJECT_ROOT / "data" / "sample")

    download_start_month: str = Field(default="2024-01")
    download_end_month: str = Field(default="2024-03")
    taxi_types: str = Field(default="yellow")
    http_timeout: int = Field(default=300, ge=10, le=3600)

    log_level: str = Field(default="INFO")

    @field_validator("download_start_month", "download_end_month")
    @classmethod
    def _validate_month(cls, v: str) -> str:
        try:
            year, month = v.split("-")
            date(int(year), int(month), 1)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Month must be in YYYY-MM format, got {v!r}") from e
        return v

    @property
    def taxi_type_list(self) -> list[str]:
        return [t.strip().lower() for t in self.taxi_types.split(",") if t.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        configure_logging(_settings.log_level)
    return _settings


def configure_logging(level: str = "INFO") -> None:
    """Configure loguru with a single console sink at the given level."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        ),
    )
