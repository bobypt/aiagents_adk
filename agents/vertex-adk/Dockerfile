FROM python:3.11-slim AS base

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

COPY src ./src

ENV PORT=8080 \
    PYTHONUNBUFFERED=1

CMD ["uv", "run", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8080"]


