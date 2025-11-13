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
cd gmail-agent
uv sync
```

### 2. Run locally

```bash
export GEMINI_API_KEY=your-gemini-api-key
export GMAIL_CLIENT_ID=your-client-id
export GMAIL_CLIENT_SECRET=your-client-secret
export GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-refresh-token

uv run uvicorn src.main:app --reload --port 8080
```

Visit http://localhost:8080 to see the API.

### 3. Deploy to Cloud Run

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1  # optional, defaults to us-central1
export SERVICE_NAME=gmail-agent  # optional, defaults to gmail-agent

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

### Process Unread Emails

```bash
# check env vlaues
gcloud run services describe gmail-agent \
  --project=loanstax-agentic-ai \
  --region=us-central1 \
  --format='json(spec.template.spec.containers[0].env)'\

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

For the `/agent/process-unread` endpoint to work, you need to configure Gmail API credentials:

1. **Gmail OAuth Credentials** (set in Cloud Run):
   ```bash
   GMAIL_CLIENT_ID=your-client-id
   GMAIL_CLIENT_SECRET=your-client-secret
   GMAIL_TOKEN_URI=https://oauth2.googleapis.com/token  # optional, defaults to this
   GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-refresh-token
   ```

   Note: The refresh token environment variable name is based on the email address:
   - Email: `hello@kagence.ai` → Variable: `GMAIL_REFRESH_TOKEN_hello_kagence_ai`
   - Replace `@` with `_` and `.` with `_`

2. **Gemini API Key** (for LangChain):
   ```bash
   GEMINI_API_KEY=your-gemini-api-key
   # OR
   GOOGLE_API_KEY=your-gemini-api-key
   ```

3. **Optional Configuration**:
   ```bash
   PROJECT_ID=your-gcp-project-id
   GEMINI_MODEL=gemini-2.5-flash  # optional, defaults to gemini-2.5-flash
   ```

### Setting Environment Variables in Cloud Run

After deployment, set environment variables. You can do this in one of two ways:

**Option 1: Single command (all variables as comma-separated string):**

```bash
gcloud run services update gmail-agent \
  --project=$PROJECT_ID \
  --region=$REGION \
  --update-env-vars="GEMINI_API_KEY=your-key,GMAIL_CLIENT_ID=your-id,GMAIL_CLIENT_SECRET=your-secret,GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-token"
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
  --update-env-vars="GMAIL_REFRESH_TOKEN_hello_kagence_ai=your-token"
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
