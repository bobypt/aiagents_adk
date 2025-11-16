# Local Gmail Consent App

This is a minimal local app that:

- Starts a Google OAuth flow for Gmail scopes
- Captures a long-lived refresh token on callback
- Stores it into Secret Manager in your GCP project

No Pub/Sub or agent logic is included.

## Prerequisites

- OAuth client JSON file at `services/receiver/oauth-client.json` (Web client)
- Google Cloud project ID with Secret Manager API enabled
- Authenticated gcloud (for your local ADC)

## Configure

Set environment variables (via shell or `.env`):

- `PROJECT_ID` (required): your GCP project ID
- `OAUTH_CLIENT_FILE` (optional, default: `oauth-client.json`)
- `REFRESH_TOKEN_SECRET_NAME` (optional, default: `gmail-refresh-tokens`)

The app will create the secret if it does not exist and add a new version per consent.

## Run locally

```bash
gcloud auth application-default login

cd agents/email_responder/gmail-consent-app

export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1
export OAUTH_CLIENT_FILE=oauth-client.json
export REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens-test
uv sync
./dev.sh
```

- Health: `http://localhost:8080/healthz`
- Start consent: `http://localhost:8080/oauth/start`

When the consent completes, the callback will:
- Fetch the user’s email
- Store `{"email": "...", "refresh_token": "..."}` in Secret Manager secret `gmail-refresh-tokens` (or your override)

## Notes

- If you don’t receive a refresh token, try again; ensure `prompt=consent` is present and the OAuth client is a Web client with your callback URL allowed (localhost).
- Tokens can be revoked by the user or expire due to inactivity. Re-run the flow to re-issue. 
