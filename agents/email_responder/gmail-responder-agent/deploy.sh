#!/usr/bin/env bash
set -euo pipefail

# Simple Cloud Run deployment script
PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID environment variable}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-agent}

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
  --max-instances 10

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

