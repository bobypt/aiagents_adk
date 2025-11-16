# Pub/Sub Push Subscription Fix Summary

## Problem
The Cloud Run service was returning 403 errors when Pub/Sub tried to push messages. This was caused by:

1. **Missing `PUBSUB_VERIFICATION_AUDIENCE` environment variable**: The service needs this to verify JWT tokens from Pub/Sub
2. **Missing IAM permissions**: The service account used by Pub/Sub push subscription needs `roles/run.invoker` permission
3. **Incorrect deployment script**: The deployment script didn't set the required environment variable

## Fixes Applied

### 1. Updated `services/receiver/deploy.sh`
- Now sets `PUBSUB_VERIFICATION_AUDIENCE` after deployment
- Grants the service account `roles/run.invoker` permission
- Provides clear output about next steps

### 2. Updated `services/receiver/src/app.py`
- Added better error handling for missing `PUBSUB_VERIFICATION_AUDIENCE`
- Improved error messages for JWT verification failures
- Changed 401 to 403 for authentication failures (more accurate)

### 3. Created `scripts/fix-pubsub.sh`
- Automated script to fix existing deployments
- Updates environment variables
- Grants IAM permissions
- Updates/recreates push subscription

### 4. Updated `README.md`
- Fixed the `/watch` endpoint command (removed `--audiences` flag)
- Added troubleshooting section
- Updated push subscription creation commands
- Added debugging steps

## How to Fix Your Current Deployment

### Option 1: Run the Fix Script (Recommended)
```bash
export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1

./scripts/fix-pubsub.sh
```

### Option 2: Manual Fix
```bash
export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1

# 1. Get service URL
RECEIVER_URL=$(gcloud run services describe gmail-receiver \
  --project $PROJECT_ID \
  --region $REGION \
  --format='value(status.url)')

# 2. Update service with PUBSUB_VERIFICATION_AUDIENCE
gcloud run services update gmail-receiver \
  --project $PROJECT_ID \
  --region $REGION \
  --update-env-vars "PUBSUB_VERIFICATION_AUDIENCE=$RECEIVER_URL"

# 3. Grant service account permission
gcloud run services add-iam-policy-binding gmail-receiver \
  --member="serviceAccount:gmail-receiver-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --project $PROJECT_ID \
  --region $REGION

# 4. Update push subscription
gcloud pubsub subscriptions delete gmail-notifications-push --project $PROJECT_ID 2>/dev/null || true
gcloud pubsub subscriptions create gmail-notifications-push \
  --topic gmail-notifications \
  --push-endpoint "$RECEIVER_URL/pubsub/push" \
  --push-auth-service-account gmail-receiver-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --project $PROJECT_ID
```

### Option 3: Redeploy (Future Deployments)
The updated `deploy.sh` script now handles this automatically:
```bash
export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1
export AGENT_ENDPOINT=<your-agent-endpoint>

./services/receiver/deploy.sh
```

## Verification

After applying the fix, verify it works:

1. **Check environment variables**:
   ```bash
   gcloud run services describe gmail-receiver \
     --project $PROJECT_ID \
     --region $REGION \
     --format="value(spec.template.spec.containers[0].env)" | grep PUBSUB_VERIFICATION_AUDIENCE
   ```

2. **Check IAM permissions**:
   ```bash
   gcloud run services get-iam-policy gmail-receiver \
     --project $PROJECT_ID \
     --region $REGION
   ```
   Should show `gmail-receiver-sa@...` with `roles/run.invoker`

3. **Check push subscription**:
   ```bash
   gcloud pubsub subscriptions describe gmail-notifications-push \
     --project $PROJECT_ID
   ```
   Should show the correct push endpoint and service account

4. **Test by sending an email**:
   - Send an email to the watched address
   - Check Cloud Run logs: `gcloud run services logs read gmail-receiver --project $PROJECT_ID --region $REGION --limit=20`
   - Should see successful processing (no 403 errors)

## What Changed

### Before
- `PUBSUB_VERIFICATION_AUDIENCE` was not set
- Service account didn't have `roles/run.invoker` permission
- Push subscription might have incorrect configuration
- Result: 403 errors when Pub/Sub tried to push messages

### After
- `PUBSUB_VERIFICATION_AUDIENCE` is set to the service URL
- Service account has `roles/run.invoker` permission
- Push subscription is correctly configured
- Result: Messages are successfully pushed and processed

## Next Steps

1. Run the fix script or apply the manual fix
2. Test by sending an email to the watched address
3. Monitor Cloud Run logs to verify successful processing
4. Future deployments will automatically include these fixes

## Troubleshooting

If you still see 403 errors after applying the fix:

1. **Verify environment variable is set**:
   ```bash
   gcloud run services describe gmail-receiver \
     --project $PROJECT_ID \
     --region $REGION \
     --format="value(spec.template.spec.containers[0].env)"
   ```

2. **Check logs for specific error messages**:
   ```bash
   gcloud run services logs read gmail-receiver \
     --project $PROJECT_ID \
     --region $REGION \
     --limit=50 \
     --format=json | jq '.[] | select(.textPayload | contains("403") or contains("Invalid"))'
   ```

3. **Verify service account has permission**:
   ```bash
   gcloud run services get-iam-policy gmail-receiver \
     --project $PROJECT_ID \
     --region $REGION \
     --format=json | jq '.bindings[] | select(.members[] | contains("gmail-receiver-sa"))'
   ```

4. **Test the endpoint manually** (using the replay tool):
   ```bash
   uv run tools/replay/replay.py \
     --endpoint "$RECEIVER_URL/pubsub/push" \
     --payload samples/pubsub.json
   ```
   Note: This won't work directly because it needs Pub/Sub authentication, but you can use it to test the service is accessible.

