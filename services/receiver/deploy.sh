#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-receiver}
AGENT_ENDPOINT=${AGENT_ENDPOINT:?Set AGENT_ENDPOINT}
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME:$(date +%Y%m%d%H%M%S)"

pushd "$(dirname "$0")" >/dev/null

echo "Building container image $IMAGE..."
gcloud builds submit --tag "$IMAGE" .

echo "Deploying $SERVICE_NAME to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --service-account "${SERVICE_ACCOUNT:-$SERVICE_NAME-sa@$PROJECT_ID.iam.gserviceaccount.com}" \
  --allow-unauthenticated=false \
  --set-env-vars "PROJECT_ID=$PROJECT_ID,REGION=$REGION,AGENT_ENDPOINT=$AGENT_ENDPOINT" \
  --set-secrets "OAUTH_CLIENT_SECRET_NAME=gmail-oauth-client:latest,REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens:latest"

popd >/dev/null

