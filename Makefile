.PHONY: help install run test test-unit lint format clean docker-up docker-down download query benchmark

help:
	@echo "Available targets:"
	@echo "  install      Create venv and install package with dev extras"
	@echo "  run          Run the full pipeline (download + queries + benchmark)"
	@echo "  download     Download parquet files for the configured month range"
	@echo "  query        Run all 10 analytics queries and print results"
	@echo "  benchmark    Run DuckDB vs Pandas vs Polars benchmark"
	@echo "  test         Run all tests with coverage"
	@echo "  test-unit    Run unit tests only (skip integration)"
	@echo "  lint         Run ruff and black checks"
	@echo "  format       Auto-fix lint + format issues"
	@echo "  docker-up    Start docker compose stack"
	@echo "  docker-down  Stop docker compose stack and remove volumes"
	@echo "  clean        Remove venv, caches, and generated data"

install:
	uv venv --python 3.11
	uv pip install -e ".[dev]"

run:
	uv run python -m nyc_taxi.pipeline

download:
	uv run nyc-taxi download

query:
	uv run nyc-taxi query all

benchmark:
	uv run nyc-taxi benchmark

test:
	uv run pytest --cov=src/nyc_taxi --cov-report=term-missing --cov-fail-under=70

test-unit:
	uv run pytest -m "not integration" --cov=src/nyc_taxi --cov-report=term-missing

lint:
	uv run ruff check .
	uv run black --check .

format:
	uv run ruff check --fix .
	uv run black .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down -v

clean:
	rm -rf .venv data/raw __pycache__ .pytest_cache .ruff_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.duckdb" -delete
