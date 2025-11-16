# Use official Python runtime as base
FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
# Copy pyproject.toml first, then lockfile if it exists
COPY pyproject.toml ./

# Copy lockfile separately (deploy.sh ensures it exists before build)
COPY uv.lock ./

# Install dependencies using lockfile for reproducibility
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ ./src/

# Expose port (Cloud Run uses PORT env var)
ENV PORT=8080

# Run the application
# Cloud Run provides PORT env var, default to 8080 if not set
CMD ["sh", "-c", "uv run uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
