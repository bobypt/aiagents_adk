#!/usr/bin/env bash
set -euo pipefail

# Script to fix Pub/Sub push subscription issues
# This updates the Cloud Run service with PUBSUB_VERIFICATION_AUDIENCE
# and ensures proper IAM permissions

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-receiver}
SERVICE_ACCOUNT=${SERVICE_ACCOUNT:-${SERVICE_NAME}-sa@${PROJECT_ID}.iam.gserviceaccount.com}

echo "Fixing Pub/Sub push subscription configuration..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Service: $SERVICE_NAME"
echo ""

# Get the service URL
RECEIVER_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')

if [ -z "$RECEIVER_URL" ]; then
  echo "Error: Service $SERVICE_NAME not found"
  exit 1
fi

echo "Service URL: $RECEIVER_URL"
echo ""

# 1. Update the service with PUBSUB_VERIFICATION_AUDIENCE
echo "1. Updating service with PUBSUB_VERIFICATION_AUDIENCE..."
gcloud run services update "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --update-env-vars "PUBSUB_VERIFICATION_AUDIENCE=$RECEIVER_URL"

echo "✓ Updated PUBSUB_VERIFICATION_AUDIENCE"
echo ""

# 2. Grant service account permission to invoke Cloud Run service
echo "2. Granting service account permission to invoke Cloud Run service..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" \
  --project "$PROJECT_ID" \
  --region "$REGION" || echo "Note: Service account may already have permission"

echo "✓ Granted run.invoker permission"
echo ""

# 3. Update or create push subscription
echo "3. Updating Pub/Sub push subscription..."
# Check if subscription exists
if gcloud pubsub subscriptions describe gmail-notifications-push --project "$PROJECT_ID" &>/dev/null; then
  echo "Subscription exists, updating..."
  # Delete and recreate (Pub/Sub doesn't support updating push endpoint directly)
  gcloud pubsub subscriptions delete gmail-notifications-push --project "$PROJECT_ID" || true
  sleep 2
fi

# Create push subscription
gcloud pubsub subscriptions create gmail-notifications-push \
  --topic gmail-notifications \
  --push-endpoint "$RECEIVER_URL/pubsub/push" \
  --push-auth-service-account "$SERVICE_ACCOUNT" \
  --project "$PROJECT_ID"

echo "✓ Created/updated push subscription"
echo ""

# 4. Verify configuration
echo "4. Verifying configuration..."
echo "Service environment variables:"
gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env)" | grep PUBSUB_VERIFICATION_AUDIENCE || echo "Warning: PUBSUB_VERIFICATION_AUDIENCE not found"

echo ""
echo "Subscription configuration:"
gcloud pubsub subscriptions describe gmail-notifications-push \
  --project "$PROJECT_ID" \
  --format="value(pushConfig.pushEndpoint,pushConfig.oidcToken.serviceAccountEmail)"

echo ""
echo "=========================================="
echo "Fix complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Test the push endpoint by sending an email to the watched address"
echo "2. Check Cloud Run logs:"
echo "   gcloud run services logs read $SERVICE_NAME --project $PROJECT_ID --region $REGION --limit=20"
echo "3. Check Pub/Sub topic metrics in the GCP Console"
echo ""

