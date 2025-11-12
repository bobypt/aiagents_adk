# Operational Runbook

## Overview

Automated Gmail draft generation pipeline:

1. Gmail `watch()` delivers notifications to Pub/Sub topic `gmail-notifications`
2. Cloud Run receiver verifies push JWT, stores refresh tokens, fetches the email, and invokes the Vertex ADK agent
3. Vertex ADK agent retrieves context from Vertex Matching, generates a draft, and stores it in Gmail

## Onboarding Steps

1. **Provision GCP project**
   - Enable APIs: Pub/Sub, Cloud Run, Secret Manager, Vertex AI
   - Run `scripts/bootstrap-infra.sh`
2. **Deploy services**
   - `services/receiver/deploy.sh`
   - `agents/vertex-adk/deploy.sh`
3. **OAuth consent**
   - Visit `/oauth/start`, approve Gmail scopes, verify Secret Manager entries
4. **Register Gmail watch**
   - Automatic during callback
   - Manual re-register via `POST /watch {"email":"user@example.com"}`
5. **Ingest knowledge base**
   - `uv run rag/ingest.py --project $PROJECT_ID --index-name ... --deployed-index-id ...`

## Secrets Management

- `gmail-oauth-client`: OAuth client JSON (Web application type)
- `gmail-refresh-tokens`: Append-only secret containing JSON records `{email, refresh_token}`
- Rotate secrets by adding versions; disable old versions after migration

## Monitoring & Alerting

- Enable Cloud Logging sinks for each service
- Set up Cloud Monitoring dashboards:
  - Pub/Sub push latencies
  - Vertex token usage (via `projects.locations.operations`)
  - Gmail draft creation errors
- Configure alerts for:
  - Receiver 5xx rate > 1% for 5 minutes
  - Agent latency > 5 seconds p95

## Incident Response

| Scenario | Action |
|----------|--------|
| Pub/Sub push failures | Check receiver logs, validate JWT audience, confirm service account permissions |
| OAuth failures | Verify redirect URI matches Cloud Run URL, refresh secret version |
| Receiver processing failure | Inspect Cloud Run logs; ensure Gmail scopes and refresh token available |
| Agent generation errors | Review Vertex safety filters, adjust prompt, check index readiness |
| Draft not appearing | Confirm Gmail label exists, ensure refresh token has compose scope |

## Security & Privacy

- Draft-only workflow; sending requires explicit opt-in
- No raw email bodies persisted; receiver truncates to snippet before logging
- Secrets stored in Secret Manager with least-privilege IAM
- Structured logging redacts PII (log only hashed identifiers)
- Regularly audit refresh token usage and revoke unused tokens

## Maintenance

- Weekly: rotate service account keys (if any), review Cloud Monitoring dashboard
- Monthly: re-run RAG ingestion, validate embeddings still relevant
- Quarterly: re-validate OAuth consent screen, update dependencies with `uv sync --upgrade`

## Disaster Recovery

- Pub/Sub messages retained for 7 days; replay using `tools/replay/replay.py`
- Vertex Matching backups via index export (configure in Vertex console)
- Maintain IaC scripts (`scripts/bootstrap-infra.sh`) for re-provisioning



