# Vertex ADK Agent

Lightweight FastAPI service compatible with Vertex AI Agent Builder (ADK style)
that performs retrieval-augmented generation and creates Gmail drafts.

## Responsibilities

1. Accept job payloads `{gmail_user, message}` from the receiver
2. Retrieve relevant context from Vertex Matching
3. Assemble a safety-first prompt and invoke a Vertex text model (e.g., `gemini-1.5-flash`)
4. Perform lightweight safety checks
5. Call Gmail API to create a draft (requires stored refresh token)
6. Return audit metadata

## Local Development

```bash
cd agents/vertex-adk
uv sync
export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1
uv run uvicorn src.app:app --host 0.0.0.0 --port 8090
```

## Deployment

- Package into a container and deploy to Cloud Run **or**
- Run as a Vertex AI custom container for Agent Builder

```bash
./deploy.sh
```

## Environment Variables

- `PROJECT_ID`
- `LOCATION`
- `VERTEX_INDEX_ENDPOINT` (Matching Engine endpoint resource name)
- `VERTEX_EMBEDDING_MODEL` (optional, defaults to `text-embedding-004`)
- `VERTEX_GENERATION_MODEL` (defaults to `gemini-1.5-flash`)
- `GMAIL_DRAFT_LABEL` (defaults to `auto-draft://pending-review`)
- `REFRESH_TOKEN_SECRET_NAME`
- `OAUTH_CLIENT_SECRET_NAME`



