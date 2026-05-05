# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.5.11

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN uv venv /opt/venv --python 3.12 && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache .


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app src/ ./src/
COPY --chown=app:app pyproject.toml README.md ./

RUN mkdir -p /app/data/raw /app/data/sample && chown -R app:app /app

USER app

ENTRYPOINT ["nyc-taxi"]
CMD ["--help"]
