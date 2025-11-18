
# =======================================
# Stage 1 — Build vectors (conditional)
# =======================================
FROM python:3.11-slim as builder

WORKDIR /app

# Create a virtual environment
RUN python -m venv uv
ENV PATH="/app/uv/bin:$PATH"

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy vector builder scripts
COPY rag/build_vectors.py ./rag/build_vectors.py
COPY rag/embedding_models.py ./rag/embedding_models.py
COPY input ./input

# Build args
# GOOGLE_API_KEY: Required if building vectors during Docker build
ARG GOOGLE_API_KEY

# Create output folder
RUN mkdir -p /app/output

# Copy output folder if it exists (build-docker.sh manages .dockerignore to handle both cases)
# If output exists locally, it will be copied here. 
# If output doesn't exist, build-docker.sh adds it to .dockerignore, so COPY will be skipped.
# Then we'll build vectors in the RUN command below.
COPY rag_output ./output

# Check if output folder has all required files, if not build vectors
RUN if [ -f /app/output/index.faiss ] && [ -f /app/output/metadata.json ] && [ -f /app/output/model_info.json ]; then \
        echo "✓ Using existing output folder from host"; \
    else \
        echo "✗ Output folder missing or incomplete - building vectors during Docker build..."; \
        if [ -z "$GOOGLE_API_KEY" ]; then \
            echo "ERROR: GOOGLE_API_KEY must be set as build arg to build vectors during Docker build."; \
            echo "Example: docker build --build-arg GOOGLE_API_KEY=your-key -t rag-server ."; \
            echo "OR: Use build-docker.sh which handles this automatically: ./build-docker.sh"; \
            echo "OR: Build vectors locally first: python rag/build_vectors.py --input input --output output"; \
            exit 1; \
        fi; \
        export GOOGLE_API_KEY=$GOOGLE_API_KEY; \
        python rag/build_vectors.py --input /app/input --output /app/output; \
    fi

# =======================================
# Stage 2 — Runtime API
# =======================================
FROM python:3.11-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/uv ./uv
ENV PATH="/app/uv/bin:$PATH"

# Copy API code and embedding models
COPY rag/api.py ./rag/api.py
COPY rag/embedding_models.py ./rag/embedding_models.py

# Copy precomputed vectors from builder
COPY --from=builder /app/output ./output

EXPOSE 8080
CMD ["python", "rag/api.py"]
