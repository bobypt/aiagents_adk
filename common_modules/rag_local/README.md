# RAG Docker Project

This project uses **Gemini Embedding 001** (`gemini-embedding-001`) by default for generating vector embeddings.

## Prerequisites

1. **Google API Key**: You need a `GOOGLE_API_KEY` for Gemini embeddings
   - Get one from: https://makersuite.google.com/app/apikey
   - Set it as an environment variable: `export GOOGLE_API_KEY="your-key-here"`

2. **Firebase Authentication** (Required for API access):
   - The API requires Firebase ID tokens for authentication
   - Set your Firebase project ID: `export FIREBASE_PROJECT_ID="your-firebase-project-id"`
   - You can find your project ID in Firebase Console → Project Settings
   - No service account needed - token validation only requires the project ID

3. **Install Dependencies**:

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
uv run python rag/build_vectors.py --input input --output output

# With custom dimension (768, 1536, or 3072)
uv run python rag/build_vectors.py --input input --output output --output-dimension 1536

# Or use a different model
uv run python rag/build_vectors.py --input input --output output --model-type sentence-transformers --model-name all-MiniLM-L6-v2
```

**Or using regular Python (requires manual dependency installation):**
```bash
python rag/build_vectors.py --input input --output output
```

## Running the API Server

**Using `uv run` (recommended):**
```bash
# Make sure GOOGLE_API_KEY is set
export GOOGLE_API_KEY="your-key-here"

# Set Firebase project ID (required for token validation)
export FIREBASE_PROJECT_ID="loanstax-dev"

uv run python rag/api.py
```

**Or using regular Python:**
```bash
export GOOGLE_API_KEY="your-key-here"
export FIREBASE_PROJECT_ID="loanstax-dev"
python rag/api.py
```

## Querying

The API uses **POST** requests with Firebase authentication. You need a Firebase ID token in the Authorization header.

**Example with curl:**
```bash
# Replace YOUR_FIREBASE_ID_TOKEN with an actual Firebase ID token
curl -X POST "http://localhost:8080/rag" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IjM4MDI5MzRmZTBlZWM0NmE1ZWQwMDA2ZDE0YTFiYWIwMWUzNDUwODMiLCJ0eXAiOiJKV1QifQ.eyJuYW1lIjoiU3VwcG9ydCBBZ2VudCIsInJvbGUiOiJTdXBwb3J0QWdlbnQiLCJpc3MiOiJodHRwczovL3NlY3VyZXRva2VuLmdvb2dsZS5jb20vbG9hbnN0YXgtZGV2IiwiYXVkIjoibG9hbnN0YXgtZGV2IiwiYXV0aF90aW1lIjoxNzYzNDYxNzQwLCJ1c2VyX2lkIjoiRGdMZllaTVFlNVNGQ2ZPTjM0MkF6WnV0bnlvMSIsInN1YiI6IkRnTGZZWk1RZTVTRkNmT04zNDJBelp1dG55bzEiLCJpYXQiOjE3NjM0NjE3NDAsImV4cCI6MTc2MzQ2NTM0MCwiZW1haWwiOiJzdXBwb3J0QGxvYW5zdGFjay5haSIsImVtYWlsX3ZlcmlmaWVkIjpmYWxzZSwiZmlyZWJhc2UiOnsiaWRlbnRpdGllcyI6eyJlbWFpbCI6WyJzdXBwb3J0QGxvYW5zdGFjay5haSJdfSwic2lnbl9pbl9wcm92aWRlciI6InBhc3N3b3JkIn19.n5MRmQ4OGzv6C8sEBnCH0PFVdWRGZqGSbs8RVJ8xhQgI8u13My5RVx6Vf1qhS1kLRANVfRTFYezv95NDcUoUrrKjdhkXTnHseDk4o4j0ZtuG8lWdioFMliwcuYQDI5C-L6XOPzOMnpuxYCWLahOo4aXTRaJTEFp5kbozJk7pSjkMr6sckeHb65Z8v7qZ67udItlqbnvaCJ9XtkJAodwoVhyThh15yiXVqJP8wUi0ctQ4GDAie9XNVL0_nsT1AHKWO6APZ5n4Oryj5S2QJF-rfgvl0IDcg6_HDsNfzVjUnL4ZqpVpB8qHUD6q29Wcqz-Q7JMIKbjQ1BdwNN3-sxJ6tg" \
  -d '{"query": "What are organic apples?"}'
```

**Getting a Firebase ID Token:**
- Use Firebase SDK in your client application
- For testing, you can use Firebase CLI: `firebase login:ci` (for CI/CD tokens)
- Or use Firebase Admin SDK to create custom tokens for testing

**Response format:**
```json
{
  "query": "What are organic apples?",
  "contexts": [...],
  "answer": "Based on the documents:\n\n...",
  "user_id": "firebase-user-id",
  "user_email": "user@example.com"
}
```

## Docker Build

```bash
./build-docker.sh
# docker build -t rag-server .
```

## Docker Run

**Run in foreground (Ctrl+C to stop):**
```bash
# Pass the API key and Firebase project ID
docker run --rm --name rag-server -p 8080:8080 \
  -e GOOGLE_API_KEY=$GOOGLE_API_KEY \
  -e FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID \
  rag-server
```

**Run in background (detached mode):**
```bash
# Start in background
docker run -d --name rag-server -p 8080:8080 \
  -e GOOGLE_API_KEY=$GOOGLE_API_KEY \
  -e FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID \
  rag-server

# Stop the container
docker stop rag-server

# Remove the container (if not using --rm)
docker rm rag-server
```

**Note:** The `--rm` flag automatically removes the container when it stops, so you don't need to manually clean it up.
