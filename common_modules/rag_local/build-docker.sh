#!/bin/bash
# Docker build script that handles output folder conditionally
# If output folder exists, copies it. If not, builds vectors during Docker build.

set -e

# Check if output folder exists and has required files
if [ -d "output" ] && [ -f "output/index.faiss" ] && [ -f "output/metadata.json" ] && [ -f "output/model_info.json" ]; then
    echo "✓ Output folder exists - will copy pre-built vectors (faster build)"
    # Remove output from .dockerignore if it exists, to ensure it gets copied
    if [ -f .dockerignore ]; then
        sed -i.bak '/^output$/d' .dockerignore 2>/dev/null || true
    fi
    docker build -t rag-server . "$@"
    # Restore .dockerignore backup if created
    if [ -f .dockerignore.bak ]; then
        mv .dockerignore.bak .dockerignore 2>/dev/null || true
    fi
else
    echo "✗ Output folder missing or incomplete - will build vectors during Docker build"
    if [ -z "$GOOGLE_API_KEY" ]; then
        echo "ERROR: GOOGLE_API_KEY must be set to build vectors during Docker build"
        echo "Example: export GOOGLE_API_KEY=your-key && ./build-docker.sh"
        exit 1
    fi
    # Add output to .dockerignore to skip COPY step
    if [ ! -f .dockerignore ] || ! grep -q "^output$" .dockerignore; then
        echo "output" >> .dockerignore
    fi
    docker build --build-arg GOOGLE_API_KEY="$GOOGLE_API_KEY" -t rag-server . "$@"
fi

