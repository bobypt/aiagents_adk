# Gmail Agent - Simple Cloud Run API

A minimal, self-contained Python Cloud Run service using `uv` for dependency management.

## Features

- ✅ FastAPI-based REST API
- ✅ `uv` for fast dependency management
- ✅ Simple one-command deployment
- ✅ Public API access
- ✅ Health check endpoints

## Prerequisites

- Google Cloud Project with billing enabled
- `gcloud` CLI installed and authenticated
- `uv` installed (https://github.com/astral-sh/uv)

## Quick Start

### 1. Install dependencies locally (optional)

```bash
cd gmail-agent
uv sync
```

### 2. Run locally

```bash
uv run uvicorn src.main:app --reload --port 8080
```

Visit http://localhost:8080 to see the API.

### 3. Deploy to Cloud Run

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1  # optional, defaults to us-central1
export SERVICE_NAME=gmail-agent  # optional, defaults to gmail-agent

./deploy.sh
```

That's it! The script will:
1. Generate `uv.lock` if needed
2. Build the Docker image
3. Deploy to Cloud Run with public access

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /echo` - Echo endpoint for testing

Example:
```bash
# Health check
curl https://your-service-url.run.app/health

# Echo endpoint
curl -X POST https://your-service-url.run.app/echo \
  -H "Content-Type: application/json" \
  -d '{"message": "hello world"}'
```

## Project Structure

```
gmail-agent/
├── src/
│   ├── __init__.py
│   └── main.py          # FastAPI application
├── pyproject.toml       # Dependencies
├── Dockerfile           # Container definition
├── deploy.sh            # Deployment script
└── README.md
```

## Customization

Edit `src/main.py` to add your own endpoints and logic.

## Requirements

- Python 3.11+
- Cloud Run enabled in your GCP project

