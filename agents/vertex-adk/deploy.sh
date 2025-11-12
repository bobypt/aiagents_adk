#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-vertex-adk-agent}
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
  --set-env-vars "PROJECT_ID=$PROJECT_ID,LOCATION=$REGION"

popd >/dev/null


