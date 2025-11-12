#!/usr/bin/env bash
set -euo pipefail

pushd "$(dirname "$0")" >/dev/null
uv sync
uv run uvicorn src.app:app --reload --port "${PORT:-8080}"
popd >/dev/null


