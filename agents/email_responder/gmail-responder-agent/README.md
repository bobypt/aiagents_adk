# Gmail Agent - Simple Cloud Run API with LangChain

A minimal, self-contained Python Cloud Run service using `uv` for dependency management and LangChain for email drafting.

## Features

- ✅ FastAPI-based REST API
- ✅ LangChain integration with Google Gemini for email drafting
- ✅ Gmail API integration for fetching and drafting emails
- ✅ `uv` for fast dependency management
- ✅ Simple one-command deployment
- ✅ Public API access (no security for now)
- ✅ Health check endpoints

## Prerequisites

- Google Cloud Project with billing enabled
- `gcloud` CLI installed and authenticated
- `uv` installed (https://github.com/astral-sh/uv)
- Gmail API OAuth credentials (client ID, client secret, refresh token)
- Gemini API key for LangChain

## Quick Start

### 1. Install dependencies locally (optional)

```bash
cd gmail-responder-agent
uv sync
```

### 2. Run locally

```bash
export GEMINI_API_KEY=your-gemini-api-key
export GMAIL_CLIENT_ID=your-client-id
export GMAIL_CLIENT_SECRET=your-client-secret
export GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-refresh-token

uv run python -m uvicorn  src.main:app --reload --port 8080

# stop 
Ctrl + C

pkill -f "uvicorn src.main:app"


export GMAIL_RESPONSER_AGENT_PATH=http://127.0.0.1:8080
curl -vvv $GMAIL_RESPONSER_AGENT_PATH/health
curl -vvv $GMAIL_RESPONSER_AGENT_PATH/

curl -X POST "$GMAIL_RESPONSER_AGENT_PATH/echo" \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'


curl -X POST "$GMAIL_RESPONSER_AGENT_PATH/agent/process-unread" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "hello@kagence.ai",
    "max_emails": 1,
    "label_ids": ["UNREAD", "INBOX"],
    "skip_existing_drafts": true
  }'




```

Visit http://localhost:8080 to see the API.

### 3. Deploy to Cloud Run

```bash
export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1  # optional, defaults to us-central1
export SERVICE_NAME=gmail-agent  # optional, defaults to gmail-agent

export GEMINI_MODEL=gemini-2.5-flash
export GEMINI_API_KEY=TODO

export REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens
export OAUTH_CLIENT_SECRET_NAME=gmail-oauth-client


# RAG settings
export VERTEX_EMBEDDING_MODEL="text-embedding-004"
export VERTEX_INDEX_ENDPOINT="$(gcloud ai index-endpoints list --region=us-central1 --format='value(name,displayName)' | grep -i 'gmail' | awk '{print $1}' | head -1)"
export VERTEX_DEPLOYED_INDEX_ID="$(gcloud ai index-endpoints describe "$VERTEX_INDEX_ENDPOINT" --region=us-central1 --format='value(deployedIndexes[0].id)')"


./deploy.sh
```

That's it! The script will:
1. Generate `uv.lock` if needed
2. Build the Docker image
3. Deploy to Cloud Run with public access

**Note:** After deployment, you'll need to set environment variables for Gmail and Gemini API credentials (see Configuration section).

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `POST /echo` - Echo endpoint for testing
- `POST /agent/process-unread` - Process unread emails and create draft replies

```bash
export GMAIL_RESPONSER_AGENT_PATH=https://gmail-agent-musrgne2jq-uc.a.run.app
curl -vvv $GMAIL_RESPONSER_AGENT_PATH/health
curl -vvv $GMAIL_RESPONSER_AGENT_PATH/

curl -X POST "$GMAIL_RESPONSER_AGENT_PATH/echo" \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'


```

### Process Unread Emails

```bash
# check env vlaues
gcloud run services describe gmail-agent \
  --project=loanstax-agentic-ai \
  --region=us-central1 \
  --format='json(spec.template.spec.containers[0].env)'

curl -X POST "https://gmail-agent-72679510753.us-central1.run.app/agent/process-unread" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "hello@kagence.ai",
    "max_emails": 1,
    "label_ids": ["UNREAD", "INBOX"],
    "skip_existing_drafts": true
  }'
```

**Request Body:**
- `email` (required): Email address to process unread emails for
- `max_emails` (optional, default: 20): Maximum number of emails to process (1-50)
- `label_ids` (optional, default: ["UNREAD", "INBOX"]): Gmail label IDs to filter by
- `skip_existing_drafts` (optional, default: true): Skip emails that already have drafts

**Response:**
```json
{
  "email": "hello@kagence.ai",
  "total_found": 5,
  "processed": 5,
  "succeeded": 4,
  "failed": 1,
  "results": [
    {
      "message_id": "abc123",
      "subject": "Example Subject",
      "from_address": "sender@example.com",
      "success": true,
      "draft_id": "draft123",
      "error": null
    }
  ]
}
```

## Configuration

### Environment Variables

For the `/agent/process-unread` and `/pubsub/push` to work, configure Gmail API credentials:

1. **Gmail OAuth Credentials** (set in Cloud Run):
   ```bash
   GMAIL_CLIENT_ID=your-client-id
   GMAIL_CLIENT_SECRET=your-client-secret
   GMAIL_TOKEN_URI=https://oauth2.googleapis.com/token  # optional, defaults to this
   ```

   Refresh tokens are preferably read from Secret Manager:
   ```bash
   REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens  # optional, default: gmail-refresh-tokens
   PROJECT_ID=your-gcp-project-id
   OAUTH_CLIENT_SECRET_NAME=gmail-oauth-client     # optional; secret containing OAuth client JSON
   ```
   - Secret payload format (each enabled version):
     - For refresh tokens: `{"email":"user@example.com","refresh_token":"..."}`
     - For OAuth client: supports either
       `{"installed":{...}}` or `{"web":{...}}` or just the inner object, containing at least `client_id`, `client_secret`, `token_uri`.
   - The agent matches the Gmail notification `emailAddress` to pick the token.

   Dev fallback (optional): You can still define a per-email env var instead of Secret Manager:
   ```bash
   GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-refresh-token  # email with @ and . replaced by _
   ```

2. **Gemini API Key** (for LangChain):
   ```bash
   GEMINI_API_KEY=your-gemini-api-key
   # OR
   GOOGLE_API_KEY=your-gemini-api-key
   ```

3. **Optional Configuration**:
   ```bash
   PROJECT_ID=your-gcp-project-id
   LOCATION=us-central1  # optional, defaults to us-central1
   GEMINI_MODEL=gemini-2.5-flash  # optional, defaults to gemini-2.5-flash
   ```

4. **RAG Configuration (Optional - for knowledge base integration)**:
   ```bash
   # Enable RAG by setting these environment variables
   VERTEX_INDEX_ENDPOINT=projects/your-project/locations/us-central1/indexEndpoints/your-endpoint-id
   VERTEX_DEPLOYED_INDEX_ID=gmail_rag_deployed_index
   VERTEX_EMBEDDING_MODEL=text-embedding-004  # optional, defaults to text-embedding-004
   ```
   
   **Note:** If RAG environment variables are not set, the agent will work without RAG context.
   
   To set up RAG:
   1. Create a Vertex Matching Engine index using the `rag/` folder scripts
   2. Set `VERTEX_INDEX_ENDPOINT` to the full resource name of your index endpoint
   3. Set `VERTEX_DEPLOYED_INDEX_ID` to the deployed index ID (e.g., `gmail_rag_deployed_index`)
   4. See `rag/README.md` for detailed RAG setup instructions

### Setting Environment Variables in Cloud Run

After deployment, set environment variables. You can do this in one of two ways:

**Option 1: Single command (all variables as comma-separated string):**

```bash
gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="GEMINI_API_KEY=your-key,REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens,OAUTH_CLIENT_SECRET_NAME=gmail-oauth-client,PROJECT_ID=$PROJECT_ID"
```

**Option 2: Multiple commands (update one variable at a time):**

```bash
gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="GEMINI_API_KEY=your-key"

gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="GMAIL_CLIENT_ID=your-id"

gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="GMAIL_CLIENT_SECRET=your-secret"

gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="REFRESH_TOKEN_SECRET_NAME=gmail-refresh-tokens,OAUTH_CLIENT_SECRET_NAME=gmail-oauth-client,PROJECT_ID=$PROJECT_ID"
```

**Option 3: Using --set-env-vars (replaces all existing env vars):**

```bash
gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --set-env-vars="GEMINI_API_KEY=your-key,GMAIL_CLIENT_ID=your-id,GMAIL_CLIENT_SECRET=your-secret,GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-token"
```

### Getting Gmail Refresh Token

You can use the OAuth flow from the receiver service to obtain refresh tokens, or use `gcloud` and the Gmail API directly. See the main `README.md` for OAuth setup instructions.

## Project Structure

```
gmail-agent/
├── src/
│   ├── __init__.py
│   └── main.py          # FastAPI application with LangChain
├── pyproject.toml       # Dependencies (includes LangChain)
├── Dockerfile           # Container definition
├── deploy.sh            # Deployment script
├── .gcloudignore        # Files to exclude from Cloud Build
├── .dockerignore        # Files to exclude from Docker build
├── .gitignore          # Git ignore patterns
└── README.md           # This file
```

## How It Works

1. **Fetch Unread Emails**: Uses Gmail API to fetch unread emails matching the specified labels
2. **Extract Email Content**: Parses email headers and body (supports plain text and HTML)
3. **Generate Reply with LangChain**: Uses Google Gemini via LangChain to draft professional email replies
4. **Create Gmail Draft**: Creates a draft reply in Gmail, properly threaded to the original email

## Next Steps

- **Add security**: Implement Firebase token validation or OAuth token validation for the API
- **Improve email parsing**: Enhance HTML email parsing and attachment handling
- **Add RAG context**: Integrate with Vertex Matching Engine for context-aware replies
- **Customize LangChain prompts**: Modify the email drafting prompt in `draft_email_reply()`
- **Add error handling**: Improve error handling and retry logic
- **Add monitoring**: Add Cloud Logging and Cloud Monitoring integration

## Requirements

- Python 3.11+
- Cloud Run enabled in your GCP project
- Gmail API OAuth credentials
- Gemini API key


# Pub-sub unread messages

gcloud beta monitoring time-series list \
  --project "$PROJECT_ID" \
  --filter='metric.type="pubsub.googleapis.com/subscription/num_undelivered_messages" AND resource.labels.subscription_id="gmail-notifications-push"' \
  --format='table(points[0].value, resource.labels.subscription_id)' \
  --limit=1
