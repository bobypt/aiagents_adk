# RAG Docker Project

This project uses **Gemini Embedding 001** (`gemini-embedding-001`) by default for generating vector embeddings.

## Prerequisites

1. **Google API Key**: You need a `GOOGLE_API_KEY` for Gemini embeddings
   - Get one from: https://makersuite.google.com/app/apikey
   - Set it as an environment variable: `export GOOGLE_API_KEY="your-key-here"`

2. **Install Dependencies**:

   **Using `uv` (recommended - automatically manages dependencies):**
   ```bash
   # Install uv if you don't have it: curl -LsSf https://astral.sh/uv/install.sh | sh
   # No need to manually install - uv run will handle it automatically
   ```

   **Or manually with pip:**
   ```bash
   pip install -r requirements.txt
   ```

## Building Vector Index

Build the vector index with the default model (`gemini-embedding-001`):

**Using `uv run` (recommended - no manual dependency installation needed):**
```bash
# With default settings (768 dimensions)
uv run python rag/build_vectors.py --input input --output rag_output

# With custom dimension (768, 1536, or 3072)
uv run python rag/build_vectors.py --input input --output rag_output --output-dimension 1536

# Or use a different model
uv run python rag/build_vectors.py --input input --output rag_output --model-type sentence-transformers --model-name all-MiniLM-L6-v2
```

**Or using regular Python (requires manual dependency installation):**
```bash
python rag/build_vectors.py --input input --output rag_output
```

## Running the API Server

**Using `uv run` (recommended):**
```bash
# Make sure GOOGLE_API_KEY is set
export GOOGLE_API_KEY="your-key-here"
uv run python rag/api.py
```

**Or using regular Python:**
```bash
export GOOGLE_API_KEY="your-key-here"
python rag/api.py
```

## Querying

```bash
curl "http://localhost:8080/rag?query=What%20are%20organic%20apples?"
```

## Docker Build

```bash
./build-docker.sh
# docker build -t rag-server .
```

## Docker Run

```bash
# Pass the API key as an environment variable
docker run -p 8080:8080 -e GOOGLE_API_KEY=$GOOGLE_API_KEY rag-server
```
