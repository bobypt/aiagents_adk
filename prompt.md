# Cursor prompt — Full implementation: Gmail → Pub/Sub → Cloud Run → Vertex ADK Agent → Vertex RAG → Gmail Drafts

> **Purpose:** This cursor prompt should bootstrap a developer workspace that implements an automated email-response pipeline. It includes step-by-step generation instructions, code files to create, and test plans. The agent will fetch email notifications (Gmail watch → Pub/Sub), fetch full email, run RAG retrieval from a Vertex-managed vector index, generate a draft with GrMini (or configured LLM), and save the draft in Gmail for human review.

---

## Persona for the generated assistant

* **Role:** Senior Cloud Engineer + ML infra specialist
* **Tone:** Precise, actionable, pragmatic, and security-first
* **Primary goal:** Produce runnable project scaffolding and stepwise instructions that a developer can execute with minimal manual research.

---

# Tech
 - Deploy to GCP
 - Prefer cloud run wherever possible
 - leverage ADK for agent capabilities and MCP to industry standard.

## High-level objectives (what the cursor-runner should produce)

1. Working Cloud Run webhook (Node or Python) that receives Pub/Sub push notifications.
2. OAuth flow for Gmail, storing refresh tokens securely in Secret Manager and linking to `watch()` registration.
3. Pub/Sub topic + subscription and secure configuration (IAM policy snippet).
4. Cloud Task / Worker pattern to reliably fetch full Gmail message after notification.
5. Vertex ADK agent skeleton that: fetches full message using Gmail API, runs RAG retrieval using Vertex Matching (or pgvector fallback), calls GrMini LLM for draft generation with safety prompts, creates a Gmail Draft (not send), and records audit logs.
6. RAG creation pipeline: extract KB docs, chunk & embed, upsert to Vertex Matching (or pgvector) and sample queries.
7. CI/test harness (local emulator where possible) and a replay tool to resend notifications for debugging.
8. Security, observability, and operational runbook sections.

---

## Output artifacts to generate

* `services/receiver/` — Cloud Run push receiver app (Node/Python) with verification + enqueue agent job.
* `agents/vertex-adk/` — ADK agent code (Python) to perform RAG + LLM generation and call Gmail Drafts API.
* `rag/` — ETL scripts to ingest documents, chunk, embed, and upsert to Vertex Matching, plus sample queries.
* `tools/replay/` — small CLI to replay Pub/Sub notifications for testing.
* `docs/runbook.md` — security, privacy, consent, and operational steps.
* `tests/` — unit + integration tests and a sandbox Gmail account test plan.

---

## Step-by-step instructions (cursor-runner should output these as numbered steps and implement them)

### Step 0 — Preconditions & setup

1. Expect the developer to provide:

   * Google Cloud project ID
   * GCP billing enabled
   * OAuth credentials (Client ID / Secret) pre-created in Google Cloud Console for the Gmail API (with `https://www.googleapis.com/auth/gmail.modify` and `https://www.googleapis.com/auth/gmail.compose`).
2. CLI tools available locally: `gcloud`, `node`/`npm` or `python3`, `docker`.


* Create `infra/main.tf` that defines:

  * Pub/Sub topic `gmail-notifications`.
  * Pub/Sub subscription `gmail-notifications-push` configured to push to Cloud Run service URL with a verified JWT requirement.
  * Cloud Run service `gmail-receiver` with `--ingress=internal` or `allow-unauthenticated=false` and a service account.
  * Secret Manager secret for storing refresh tokens or application state.
  * Optional: Cloud SQL (Postgres) + pgvector extension if using pgvector instead of Vertex Matching.
* Add IAM bindings so only Gmail service and your service account can publish/receive.


### Step 2 — OAuth flow and `watch()` registration

* Create `services/receiver/src/oauth.js` (or `oauth.py`) that:

  * Implements standard OAuth2 consent flow for Gmail (webserver + redirect URI pointing to Cloud Run receiver `/oauth/callback`).
  * Exchanges code for refresh token and stores token in Secret Manager keyed by `gmail_user_id`.
  * Calls `gmail.users.watch` for that user, pointing to the Pub/Sub topic created earlier; persist returned `historyId` in a small DB or Secret Manager entry.
* Cursor should produce curl/httpie examples and a local dev run mode using `oauthlib` or `google-auth-library`.

### Step 3 — Cloud Run receiver: verify push, fetch Gmail, trigger agent

* Receiver responsibilities:

  1. Accept Pub/Sub push POSTs and verify JWT/push header signature (or, if using pull, authenticate and pull messages).
  2. Parse message: extract `message.data` base64 decoded JSON which contains `emailAddress`, `historyId`, and `messageId` hints.
  3. Use the stored refresh token to obtain an access token for the Gmail API and fetch the full message (`users.messages.get`).
  4. Sanitize the payload (trim body, headers) and invoke the Vertex ADK agent endpoint directly.
* Provide a `Dockerfile` and `entrypoint` for Cloud Run.

### Step 4 — RAG pipeline: ingest, chunk, embed, upsert to Vertex Matching (or pgvector)

* ETL script responsibilities (`rag/ingest.py`):

  1. Accept a data source folder (`docs/`), split documents into chunks with overlap (e.g., 500 token chunks with 50 token overlap).
  2. Generate embeddings using either Vertex Embeddings API or an in-project embedding model.
  3. Upsert vectors to Vertex Matching index (preferred) or into Postgres + pgvector if the customer prefers self-managed.
  4. Save mapping metadata (source doc id, chunk id, text snippet, URL) for provenance.
* Provide sample code for Vertex Matching upsert (REST snippets / python client) and fallback instructions for pgvector + cloudsql upsert.

### Step 5 — ADK Agent: RAG + LLM -> draft generation

* Agent flow:

  1. Accept job payload: `{gmail_user_id, message_id, message_meta, sanitized_snippet}`.
  2. Perform retrieval: Query Vertex Matching with the email text as the query, fetch top-K docs (K configurable), and attach provenance metadata to each retrieved snippet.
  3. Construct a safe prompt template that includes:

     * System instructions (safety, role: `You are an assistant that drafts email replies using the provided trusted sources. Always include citations and a confidence score.`)
     * Retrievals (each with doc id and 2-3 sentence chunk)
     * The incoming email text (sanitized)
     * Explicit constraints (no automatic sending, detect PII, do not hallucinate, include suggested subject and placeholders)
  4. Call Vertex's text generation model (e.g., GrMini) and capture response, token usage, and latency.
  5. Sanity-check output via a small classifier: banlists, PII leak detection, prompt-injection markers.
  6. Create a Gmail Draft via Gmail API `drafts.create` including: `to`, `cc`, `subject`, `body` and JSON metadata in a header or special footer containing provenance.
  7. Persist audit record and return job status.
* Provide ADK skeleton code (Python) demonstrating retrieval, prompt assembly, LLM call, and Gmail Draft creation.

### Step 6 — Human-in-the-loop UI & notifications

* Provide simple options:

  * Send notification to Slack or email with link to Gmail Draft for review.
  * Add Gmail label `auto-draft://pending-review` to the draft or conversation.
* Provide sample webhook integration (Slack) and a small moderation UI (optional) built with static HTML + Firebase Auth or simple Cloud Run UI.

### Step 7 — Monitoring, logging, cost controls

* Suggestions to implement:

* Cloud Logging with structured logs for each job: inputs (sanitized), retrieved doc ids, LLM choices, token usage, and outcome.
* Cloud Monitoring alerts for LLM spend, error rate.
* Daily spending cap via billing alerts and programmatic throttles in the agent.

### Step 8 — Tests & replay

* Implement `tools/replay/` which takes saved notifications and replays them to the Cloud Run receiver for debugging.
* Integration tests that run against a sandbox Gmail account and a local Vertex Matching test index (or mocked responses).

---

## Security, Privacy & Compliance checklist (cursor should generate this as a standalone `docs/runbook.md` section)

* OAuth consent screen configured and published for internal use or external if needed.
* Store Gmail refresh tokens in Secret Manager with access only to the service accounts used by the receiver/agent.
* Redact PII from logs: never log full email bodies; log only hashed ids and short sanitized snippets.
* Maintain a consent record for each connected mailbox with timestamp and scope.
* Policy: drafts-only by default. Auto-send only allowed under opt-in and whitelist rules.
* Hard limit on attachments handled by agent and timeouts for LLM calls.

---

## Cursor prompt: concrete prompt to pass to code-generation tool

```
You are a senior cloud engineer and ML infra specialist. Produce a full repository scaffold (file tree + file contents) that implements an automated email responder pipeline. The repository must be runnable end-to-end in a Google Cloud project and include the following components:

- `services/receiver/` Cloud Run app that verifies Pub/Sub push JWT, persists notification to Firestore/Cloud SQL, and enqueues Cloud Tasks. Include Dockerfile and local dev instructions.
- `services/receiver/` that handles Pub/Sub pushes, fetches Gmail messages using stored refresh tokens, sanitizes the payload, and calls `agents/vertex-adk`.
- `agents/vertex-adk/` ADK-compatible Python agent that retrieves KB documents from Vertex Matching, composes a safety-first prompt, calls Vertex text generation (GrMini or configured LLM), runs a classifier to detect hallucinations or PII, and creates a Gmail draft (not send). Include unit tests and CI workflow.
- `rag/` ingestion scripts to chunk, embed (Vertex Embeddings), and upsert to Vertex Matching. Provide fallback instructions to use pgvector + cloudsql instead.
- `tools/replay/` script for replaying Pub/Sub notifications and local integration tests.

Constraints and guardrails:
- Draft-only default. Never send automatically unless explicitly enabled and whitelisted.
- Use Secret Manager for all secrets. Do not print or persist raw tokens in logs.
- Include instructions for `watch()` registration per mailbox and history-based catchup using `users.history.list`.
- Implement idempotency on notification processing using `gmail_user_id + message_id`.

For each file in the scaffold, include a short comment header describing its purpose and a minimal, runnable implementation with dependency specifications (package.json or requirements.txt). Also include clear `README.md` with step-by-step commands to deploy infra, run the OAuth flow, start the receiver, ingest sample KB docs, and run the agent in test mode.

Return: a zip-ready tree with all file contents in markdown code fences, plus a short verification checklist and sample commands to run the end-to-end pipeline in a dev project.
```

---

## Final checklist for the developer (quick runbook)

2. Deploy Cloud Run `services/receiver` and `agents/vertex-adk`.
3. Run OAuth flow against the Cloud Run receiver `/oauth/start` and finish consent to store refresh token + `watch()` registration.
4. Run `rag/ingest.py --source docs/` to populate Vertex Matching.
5. Send a test email to the sandbox Gmail account. Confirm Pub/Sub notification arrives, Cloud Run processes it, receiver fetches message, ADK agent generates a draft and persists it to Gmail Drafts.
6. Inspect logs and the audit trail for provenance and token usage.

---

## Extras for the cursor-runner (optional enhancements)

* Implement a small web UI for approving drafts and optionally allowing auto-send on a per-sender whitelist.
* Add throttling & batching for embedding/upsert jobs.
* Add an explainability layer: an automatic 2-3 sentence summary explaining *why* certain retrievals were used in the draft.

---

End of prompt document.
