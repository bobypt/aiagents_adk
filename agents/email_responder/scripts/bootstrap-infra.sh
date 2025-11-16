#!/usr/bin/env bash
set -euo pipefail

# Bootstrap minimal GCP infrastructure for the Gmail RAG pipeline.
# Creates Pub/Sub topic and push subscription, service accounts, and Cloud Run services.

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}

TOPIC=gmail-notifications
SUBSCRIPTION=gmail-notifications-push
RECEIVER_SA=gmail-receiver-sa
AGENT_SA=vertex-adk-agent-sa

echo "Using project: $PROJECT_ID ($REGION)"

gcloud config set project "$PROJECT_ID" >/dev/null

echo "Creating service accounts..."
gcloud iam service-accounts create "$RECEIVER_SA" --display-name "Gmail Receiver" || true
gcloud iam service-accounts create "$AGENT_SA" --display-name "Vertex ADK Agent" || true

RECEIVER_SA_EMAIL="$RECEIVER_SA@$PROJECT_ID.iam.gserviceaccount.com"
AGENT_SA_EMAIL="$AGENT_SA@$PROJECT_ID.iam.gserviceaccount.com"

echo "Creating Pub/Sub topic $TOPIC..."
gcloud pubsub topics create "$TOPIC" --project "$PROJECT_ID" || true

echo "Granting Pub/Sub publish permission to Gmail API service account..."
# Gmail uses this service account to publish notifications
gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project "$PROJECT_ID" || true

echo "Reminder: deploy gmail-receiver before creating push subscription."

echo "Creating Secrets placeholders..."
gcloud secrets create gmail-oauth-client --replication-policy=automatic --project "$PROJECT_ID" || true
gcloud secrets create gmail-refresh-tokens --replication-policy=automatic --project "$PROJECT_ID" || true

echo "Granting Secret Manager access to service accounts..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RECEIVER_SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor" >/dev/null || true
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$AGENT_SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor" >/dev/null || true

echo "Bootstrap complete."


