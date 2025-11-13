#!/usr/bin/env bash
set -euo pipefail

# Script to update Cloud Run environment variables for gmail-agent
PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID environment variable}
REGION=${REGION:-us-central1}
SERVICE_NAME=${SERVICE_NAME:-gmail-agent}

echo "Updating environment variables for $SERVICE_NAME..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Check if all required variables are set
if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "Warning: GEMINI_API_KEY not set"
fi
if [ -z "${GMAIL_CLIENT_ID:-}" ]; then
    echo "Warning: GMAIL_CLIENT_ID not set"
fi
if [ -z "${GMAIL_CLIENT_SECRET:-}" ]; then
    echo "Warning: GMAIL_CLIENT_SECRET not set"
fi

# Build env vars string
ENV_VARS=""
[ -n "${GEMINI_API_KEY:-}" ] && ENV_VARS="${ENV_VARS}GEMINI_API_KEY=${GEMINI_API_KEY},"
[ -n "${GMAIL_CLIENT_ID:-}" ] && ENV_VARS="${ENV_VARS}GMAIL_CLIENT_ID=${GMAIL_CLIENT_ID},"
[ -n "${GMAIL_CLIENT_SECRET:-}" ] && ENV_VARS="${ENV_VARS}GMAIL_CLIENT_SECRET=${GMAIL_CLIENT_SECRET},"
[ -n "${GMAIL_TOKEN_URI:-}" ] && ENV_VARS="${ENV_VARS}GMAIL_TOKEN_URI=${GMAIL_TOKEN_URI},"

# Add refresh tokens (look for GMAIL_REFRESH_TOKEN_* variables)
for var in $(env | grep "^GMAIL_REFRESH_TOKEN_" | cut -d= -f1); do
    value=$(eval echo \$$var)
    ENV_VARS="${ENV_VARS}${var}=${value},"
done

# Remove trailing comma
ENV_VARS="${ENV_VARS%,}"

if [ -z "$ENV_VARS" ]; then
    echo "Error: No environment variables to set"
    echo "Set at least one of: GEMINI_API_KEY, GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN_*"
    exit 1
fi

echo "Updating environment variables..."
echo "Variables: $ENV_VARS"
echo ""

gcloud run services update "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --update-env-vars="$ENV_VARS"

echo ""
echo "✅ Environment variables updated!"
echo ""
echo "To verify, run:"
echo "  gcloud run services describe $SERVICE_NAME --project $PROJECT_ID --region $REGION --format='value(spec.template.spec.containers[0].env)'"

