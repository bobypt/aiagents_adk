#!/usr/bin/env bash
set -euo pipefail

# Simple Cloud Run deployment script
PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID environment variable}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-agent}
OAUTH_CLIENT_SECRET_NAME=${OAUTH_CLIENT_SECRET_NAME:-gmail-oauth-client}
REFRESH_TOKEN_SECRET_NAME=${REFRESH_TOKEN_SECRET_NAME:-gmail-refresh-tokens}

echo "Deploying $SERVICE_NAME to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Generate lockfile if it doesn't exist (required for Docker build)
if [ ! -f "uv.lock" ]; then
    echo "Generating uv.lock..."
    uv lock
    echo "✓ Lockfile generated"
fi

# Build and deploy
echo "Building Docker image..."
gcloud builds submit --tag "gcr.io/$PROJECT_ID/$SERVICE_NAME:latest" .

# Deploy to Cloud Run with public access
# Collect environment variables to set on the service
ENV_VARS="PROJECT_ID=$PROJECT_ID"
[ -n "${REGION:-}" ] && ENV_VARS="$ENV_VARS,LOCATION=$REGION"
[ -n "${REFRESH_TOKEN_SECRET_NAME:-}" ] && ENV_VARS="$ENV_VARS,REFRESH_TOKEN_SECRET_NAME=$REFRESH_TOKEN_SECRET_NAME"
[ -n "${GEMINI_API_KEY:-}" ] && ENV_VARS="$ENV_VARS,GEMINI_API_KEY=$GEMINI_API_KEY"
[ -n "${GEMINI_MODEL:-}" ] && ENV_VARS="$ENV_VARS,GEMINI_MODEL=$GEMINI_MODEL"
[ -n "${OAUTH_CLIENT_SECRET_NAME:-}" ] && ENV_VARS="$ENV_VARS,OAUTH_CLIENT_SECRET_NAME=$OAUTH_CLIENT_SECRET_NAME"
# Optional RAG
[ -n "${VERTEX_INDEX_ENDPOINT:-}" ] && ENV_VARS="$ENV_VARS,VERTEX_INDEX_ENDPOINT=$VERTEX_INDEX_ENDPOINT"
[ -n "${VERTEX_DEPLOYED_INDEX_ID:-}" ] && ENV_VARS="$ENV_VARS,VERTEX_DEPLOYED_INDEX_ID=$VERTEX_DEPLOYED_INDEX_ID"
[ -n "${VERTEX_EMBEDDING_MODEL:-}" ] && ENV_VARS="$ENV_VARS,VERTEX_EMBEDDING_MODEL=$VERTEX_EMBEDDING_MODEL"

echo "Setting environment variables on service:"
echo "  $ENV_VARS"

gcloud run deploy "$SERVICE_NAME" \
  --image "gcr.io/$PROJECT_ID/$SERVICE_NAME:latest" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --set-env-vars "$ENV_VARS"

# Get service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')

echo ""
echo "✅ Deployment complete!"
echo "Service URL: $SERVICE_URL"
echo ""
echo "Test the API:"
echo "  curl $SERVICE_URL/health"
echo "  curl -X POST $SERVICE_URL/echo -H 'Content-Type: application/json' -d '{\"message\":\"hello\"}'"

