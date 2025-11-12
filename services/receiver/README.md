# Gmail Receiver Service

Cloud Run service that:

1. Handles Pub/Sub push notifications from Gmail `watch()` registrations
2. Hosts OAuth 2.0 endpoints for user consent and watch registration
3. Fetches Gmail messages and invokes the Vertex ADK agent directly

## Local Development

```bash
cd services/receiver
uv sync
uv run uvicorn src.app:app --reload --port 8080
```

- Visit `http://localhost:8080/healthz` for a readiness check
- Start OAuth flow at `http://localhost:8080/oauth/start`

Set environment variables via `.env` (automatically loaded):

- `PROJECT_ID`
- `REGION` (default: `us-central1`)
- `PUBSUB_VERIFICATION_AUDIENCE` (Cloud Run receiver service account email)
- `OAUTH_CLIENT_SECRET_NAME` (Secret Manager resource name)
- `REFRESH_TOKEN_SECRET_NAME` (Secret Manager resource name)
- `AGENT_ENDPOINT` (HTTP endpoint for the Vertex ADK agent)

## Deployment

```bash
./deploy.sh
```

`deploy.sh` builds an artifact registry image with `gcloud builds submit` and deploys to Cloud Run.



