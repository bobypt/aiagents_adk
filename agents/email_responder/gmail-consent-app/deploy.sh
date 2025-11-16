#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-receiver}
AGENT_ENDPOINT=${AGENT_ENDPOINT:?Set AGENT_ENDPOINT}
SERVICE_ACCOUNT=${SERVICE_ACCOUNT:-${SERVICE_NAME}-sa@${PROJECT_ID}.iam.gserviceaccount.com}
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME:$(date +%Y%m%d%H%M%S)"

pushd "$(dirname "$0")" >/dev/null

echo "Building container image $IMAGE..."
gcloud builds submit --tag "$IMAGE" .

echo "Deploying $SERVICE_NAME to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --service-account "$SERVICE_ACCOUNT" \
  --no-allow-unauthenticated \
  --set-env-vars "PROJECT_ID=$PROJECT_ID,REGION=$REGION,AGENT_ENDPOINT=$AGENT_ENDPOINT,OAUTH_CLIENT_SECRET_NAME=gmail-oauth-client,REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens"

# Get the service URL after deployment
RECEIVER_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')

echo "Service URL: $RECEIVER_URL"

# Update the service with PUBSUB_VERIFICATION_AUDIENCE
# Note: Pub/Sub sets the audience to the full push endpoint URL, not just the service URL
echo "Updating service with PUBSUB_VERIFICATION_AUDIENCE..."
PUSH_ENDPOINT="${RECEIVER_URL}/pubsub/push"
gcloud run services update "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --update-env-vars "PUBSUB_VERIFICATION_AUDIENCE=$PUSH_ENDPOINT"

# Grant the service account permission to invoke itself (needed for Pub/Sub push)
echo "Granting service account permission to invoke Cloud Run service..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" \
  --project "$PROJECT_ID" \
  --region "$REGION" || echo "Note: Service account may already have permission"

echo "Deployment complete!"
echo "Service URL: $RECEIVER_URL"
echo "Next: Create/update Pub/Sub push subscription with this URL"

popd >/dev/null

