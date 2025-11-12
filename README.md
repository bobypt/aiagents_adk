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
  - `https://www.googleapis.com/auth/gmail.modify`
  - `https://www.googleapis.com/auth/gmail.compose`

### Quickstart

1. **Clone and set environment**
   ```bash
   export PROJECT_ID=loanstax-agentic-ai
   export REGION=us-central1
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
   - Secret placeholders for OAuth config and refresh tokens

4. **Deploy receiver and agent**
   ```bash
   export AGENT_ENDPOINT=$(gcloud run services describe vertex-adk-agent --project $PROJECT_ID --region $REGION --format='value(status.url)')/agent/run
   ./services/receiver/deploy.sh
   ./agents/vertex-adk/deploy.sh
   ```

5. **Create Pub/Sub push subscription**
   ```bash
   RECEIVER_URL=$(gcloud run services describe gmail-receiver --project $PROJECT_ID --region $REGION --format='value(status.url)')
   gcloud pubsub subscriptions create gmail-notifications-push \
     --topic gmail-notifications \
     --push-endpoint "$RECEIVER_URL/pubsub/push" \
     --push-auth-service-account gmail-receiver-sa@$PROJECT_ID.iam.gserviceaccount.com
   ```

6. **Run OAuth consent flow locally**
   ```bash
   ./services/receiver/dev.sh
   # Visit http://localhost:8080/oauth/start, authenticate, and store refresh token in Secret Manager.
   ```

7. **Register Gmail watch**
   After consent, the receiver automatically calls `users.watch`. You can re-run manually with:
   ```bash
   curl -X POST https://<receiver-url>/watch -H "Authorization: Bearer <ID_TOKEN>" -d '{"email":"you@example.com"}'
   ```

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
     --endpoint https://gmail-receiver-<hash>-uc.a.run.app \
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

### Next Steps

- Add automated CI pipeline (GitHub Actions / Cloud Build)
- Instrument structured logging and monitoring alerts
- Extend to Slack notifications or moderation UI (`services/ui/`)
- Configure cost controls and daily auditing

Refer to `docs/runbook.md` for detailed operational procedures.
# aiagents_adk