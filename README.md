## Gmail RAG Auto-Drafter

Bootstrap scaffolding for an automated Gmail reply workflow on Google Cloud:

- Gmail watch → Pub/Sub push → Cloud Run receiver (`services/receiver`)
- Vertex ADK agent (`agents/vertex-adk`) performs retrieval-augmented generation with Vertex AI and saves a Gmail draft
- `rag/` scripts ingest knowledge base docs into Vertex Matching
- `tools/replay/` replays Pub/Sub push payloads for debugging
- `docs/runbook.md` captures security and operational guidance

### Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI ≥ 460.0.0
- `uv` (https://github.com/astral-sh/uv) for Python environment management
- `npm` ≥ 9 if you extend tooling with TypeScript
- OAuth 2.0 Web Client configured for Gmail API scopes:
  - `https://www.googleapis.com/auth/gmail.compose`
  - `https://www.googleapis.com/auth/gmail.modify`
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/userinfo.email`

### Quickstart

1. **Clone and set environment**
   ```bash
   export PROJECT_ID=loanstax-agentic-ai
   export REGION=us-central1

   gcloud auth application-default login


   ```

2. **Enable APIs**
   ```bash
   gcloud services enable \
     pubsub.googleapis.com \
     run.googleapis.com \
     secretmanager.googleapis.com \
     aiplatform.googleapis.com \
     notebooks.googleapis.com
   ```

3. **Bootstrap Pub/Sub + Cloud Run services**
   ```bash
   ./scripts/bootstrap-infra.sh
   ```
   The script creates:
   - Pub/Sub topic `gmail-notifications`
   - Service accounts for the receiver and agent
   - Secret placeholders (and grants Secret Manager access to those service accounts) for OAuth config and refresh tokens
   > **Note:** grant the user or CI principal that runs `gcloud run deploy` the `roles/iam.serviceAccountUser` role on `gmail-receiver-sa` (and `vertex-adk-agent-sa`) so it can act-as the service account during deployment.
   The script creates:
   - Pub/Sub topic `gmail-notifications`
   - Service accounts for the receiver and agent
   - Secret placeholders for OAuth config and refresh tokens

4. **Load OAuth client and run consent flow locally**
   ```bash
   # create an oAuth client in GCP console
   
   # upload your OAuth client JSON (download from Google Cloud Console)
   printf '%s' "$(cat services/receiver/oauth-client.json)" | \
     gcloud secrets versions add gmail-oauth-client \
       --data-file=- \
       --project=$PROJECT_ID

   ./services/receiver/dev.sh
   # Visit http://localhost:8080/oauth/start, authenticate, and store the refresh token in Secret Manager.
   # After success, stop the dev server (Ctrl+C).


   # verify 
   gcloud secrets versions access latest --secret=gmail-refresh-tokens --project=loanstax-agentic-ai



   ```
   This seeds `gmail-refresh-tokens` with the first version so Cloud Run can mount it.

5. **Deploy receiver and agent**
   ```bash
   
   ./services/receiver/deploy.sh
   ./agents/vertex-adk/deploy.sh

   export AGENT_ENDPOINT=$(gcloud run services describe vertex-adk-agent --project $PROJECT_ID --region $REGION --format='value(status.url)')/agent/run

   ```

6. **Create/Update Pub/Sub push subscription**
   ```bash
   RECEIVER_URL=$(gcloud run services describe gmail-receiver --project $PROJECT_ID --region $REGION --format='value(status.url)')
   
   # Delete existing subscription if it exists (to update it)
   gcloud pubsub subscriptions delete gmail-notifications-push --project $PROJECT_ID 2>/dev/null || true
   
   # Create push subscription
   gcloud pubsub subscriptions create gmail-notifications-push \
     --topic gmail-notifications \
     --push-endpoint "$RECEIVER_URL/pubsub/push" \
     --push-auth-service-account gmail-receiver-sa@$PROJECT_ID.iam.gserviceaccount.com \
     --project $PROJECT_ID
   ```

7. **Register Gmail watch**
   After consent, the receiver automatically calls `users.watch`. You can re-run manually with:
   ```bash
   RECEIVER_URL=$(gcloud run services describe gmail-receiver \
     --project=$PROJECT_ID \
     --region=$REGION \
     --format='value(status.url)')

   # Get identity token (without --audiences for user accounts)
   ID_TOKEN=$(gcloud auth print-identity-token)

   # Register watch
   curl -X POST "$RECEIVER_URL/watch" \
     -H "Authorization: Bearer $ID_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"email":"your-email@example.com"}'
   ```
   **Note:** Replace `your-email@example.com` with the email address you used during OAuth consent.

8. **Ingest knowledge base**
   ```bash
   uv run rag/ingest.py \
     --project $PROJECT_ID \
     --location us-central1 \
     --index-name projects/$PROJECT_ID/locations/us-central1/indexes/your-index \
     --source docs/kb
   ```

9. **Replay notifications for testing**
   ```bash
   uv run tools/replay/replay.py \
     --endpoint https://gmail-receiver-musrgne2jq-uc.a.run.app \
     --payload samples/pubsub.json
   ```

### Directory Overview

- `services/receiver/`: Pub/Sub push handler, OAuth endpoints, Gmail fetch, agent trigger
- `agents/vertex-adk/`: Vertex ADK-based RAG agent
- `rag/`: Knowledge base ingestion and sample docs
- `tools/replay/`: CLI utilities for debugging Pub/Sub workflow
- `scripts/`: Infrastructure bootstrap helpers
- `docs/`: Runbook and architecture notes

### Verification Checklist

- [ ] Pub/Sub push receives JWT-verified notifications
- [ ] OAuth flow stores refresh token in Secret Manager
- [ ] Receiver fetches Gmail message bodies successfully
- [ ] Vertex Matching contains KB documents and retrieval returns top-K snippets
- [ ] Agent generates drafts with provenance and safety filters
- [ ] Drafts land in Gmail with `auto-draft://pending-review` label
- [ ] Runbook reviewed for security/compliance alignment

### Troubleshooting

#### Pub/Sub Push Subscription Issues (403 Errors)

If you're seeing 403 errors when Pub/Sub tries to push messages to your Cloud Run service:

1. **Fix the deployment**:
   ```bash
   # Run the fix script
   ./scripts/fix-pubsub.sh
   ```

   Or manually:
   ```bash
   # 1. Get service URL
   RECEIVER_URL=$(gcloud run services describe gmail-receiver --project $PROJECT_ID --region $REGION --format='value(status.url)')
   
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

2. **Check logs**:
   ```bash
   gcloud run services logs read gmail-receiver --project $PROJECT_ID --region $REGION --limit=20
   ```

3. **Verify configuration**:
   ```bash
   # Check environment variables
   gcloud run services describe gmail-receiver --project $PROJECT_ID --region $REGION --format="value(spec.template.spec.containers[0].env)"
   
   # Check IAM permissions
   gcloud run services get-iam-policy gmail-receiver --project $PROJECT_ID --region $REGION
   
   # Check push subscription
   gcloud pubsub subscriptions describe gmail-notifications-push --project $PROJECT_ID
   ```

#### Gmail Watch Not Triggering

1. **Check if watch is registered**:
   - Gmail watch expires after 7 days
   - Re-register using the `/watch` endpoint (see step 7)

2. **Verify email address**:
   - Use the exact email address from your refresh token
   - Check: `gcloud secrets versions access latest --secret=gmail-refresh-tokens --project $PROJECT_ID`

3. **Check Pub/Sub topic for messages**:
   ```bash
   # Create a debug pull subscription
   gcloud pubsub subscriptions create gmail-notifications-debug --topic gmail-notifications --project $PROJECT_ID
   
   # Check for messages
   gcloud pubsub subscriptions pull gmail-notifications-debug --project $PROJECT_ID --limit=10
   ```

### Next Steps

- Add automated CI pipeline (GitHub Actions / Cloud Build)
- Instrument structured logging and monitoring alerts
- Extend to Slack notifications or moderation UI (`services/ui/`)
- Configure cost controls and daily auditing

Refer to `docs/runbook.md` for detailed operational procedures.
# aiagents_adk