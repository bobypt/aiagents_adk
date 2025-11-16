#!/usr/bin/env bash
set -euo pipefail

# One-shot setup for Gmail watch -> Pub/Sub -> gmail-responder-agent
# - Creates topic and push subscription
# - Grants Gmail publisher SA
# - Points push subscription to gmail-responder-agent /pubsub/push
# - Sets PUBSUB_VERIFICATION_AUDIENCE on the service (optional for verification)
#
# Required env:
#   PROJECT_ID
# Optional:
#   REGION               (default: us-central1)
#   SERVICE_NAME         (default: gmail-agent)
#   TOPIC                (default: gmail-notifications)
#   SUBSCRIPTION         (default: gmail-notifications-push)
#
# The script will use the service's runtime service account for OIDC push tokens.

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-agent}
TOPIC=${TOPIC:-gmail-notifications}
SUBSCRIPTION=${SUBSCRIPTION:-gmail-notifications-push}

echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "Service: $SERVICE_NAME"
echo "Topic:   $TOPIC"
echo "Sub:     $SUBSCRIPTION"
echo

gcloud config set project "$PROJECT_ID" >/dev/null

echo "1) Ensure Pub/Sub topic exists..."
gcloud pubsub topics create "$TOPIC" --project "$PROJECT_ID" || true

echo "2) Grant Gmail publisher SA rights to topic..."
gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project "$PROJECT_ID" || true

echo "3) Resolve Cloud Run service URL and runtime service account..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')

if [ -z "${SERVICE_URL}" ]; then
  echo "ERROR: Cloud Run service '$SERVICE_NAME' not found in $PROJECT_ID/$REGION"
  exit 1
fi
echo "   Service URL: $SERVICE_URL"

RUNTIME_SA=$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')

if [ -z "${RUNTIME_SA}" ]; then
  # Default compute SA
  RUNTIME_SA="${PROJECT_ID}-compute@developer.gserviceaccount.com"
fi
echo "   Runtime SA: $RUNTIME_SA"

PUSH_ENDPOINT="${SERVICE_URL}/pubsub/push"

echo "4) (Optional) Set PUBSUB_VERIFICATION_AUDIENCE to the push endpoint..."
gcloud run services update "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --update-env-vars "PUBSUB_VERIFICATION_AUDIENCE=${PUSH_ENDPOINT}" || true

echo "5) Allow the runtime SA to invoke the service..."
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/run.invoker" \
  --project "$PROJECT_ID" \
  --region "$REGION" || true

echo "6) Recreate push subscription pointing to /pubsub/push..."
if gcloud pubsub subscriptions describe "$SUBSCRIPTION" --project "$PROJECT_ID" &>/dev/null; then
  gcloud pubsub subscriptions delete "$SUBSCRIPTION" --project "$PROJECT_ID" || true
  sleep 2
fi

gcloud pubsub subscriptions create "$SUBSCRIPTION" \
  --topic "$TOPIC" \
  --push-endpoint "$PUSH_ENDPOINT" \
  --push-auth-service-account "$RUNTIME_SA" \
  --project "$PROJECT_ID"

echo
echo "Done."
echo "Verify:"
echo "  gcloud pubsub topics describe $TOPIC --project $PROJECT_ID"
echo "  gcloud pubsub subscriptions describe $SUBSCRIPTION --project $PROJECT_ID"
echo "  gcloud run services describe $SERVICE_NAME --project $PROJECT_ID --region $REGION --format='value(status.url)'"
echo
echo "Next:"
echo "- Run the consent app to store a refresh token for your Gmail address."
echo "- Register Gmail watch to the topic (via your existing flow or manually)."

