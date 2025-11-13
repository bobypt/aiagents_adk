"""
Gmail Agent API service using FastAPI and LangChain for email drafting.
"""
import base64
import json
import os
from typing import Any, Dict, List, Optional

import google.auth
import google.auth.transport.requests
from fastapi import FastAPI, HTTPException
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

app = FastAPI(title="Gmail Agent API", version="0.1.0")

# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Gmail API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


class HealthResponse(BaseModel):
    status: str
    message: str


class ProcessUnreadRequest(BaseModel):
    email: str = Field(..., description="Email address to process unread emails for")
    max_emails: int = Field(default=20, ge=1, le=50, description="Maximum number of emails to process")
    label_ids: List[str] = Field(default=["UNREAD", "INBOX"], description="Gmail label IDs to filter by")
    skip_existing_drafts: bool = Field(default=True, description="Skip emails that already have drafts")


class EmailProcessingResult(BaseModel):
    message_id: str
    subject: str
    from_address: str
    success: bool
    draft_id: Optional[str] = None
    error: Optional[str] = None


class ProcessUnreadResponse(BaseModel):
    email: str
    total_found: int
    processed: int
    succeeded: int
    failed: int
    results: List[EmailProcessingResult]


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    echo: str
    original: str


# Initialize LangChain model
_llm = None


def get_llm():
    """Get or initialize LangChain Gemini model."""
    global _llm
    if _llm is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable must be set")
        _llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.4,
        )
    return _llm


def fetch_unread_messages(
    creds: Credentials,
    email: str,
    max_results: int = 20,
    label_ids: List[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch unread messages from Gmail."""
    if label_ids is None:
        label_ids = ["UNREAD"]

    gmail = build("gmail", "v1", credentials=creds)

    # Build query
    query = "is:unread"
    if "INBOX" in label_ids and "UNREAD" not in label_ids:
        query = "in:inbox is:unread"

    # List messages
    response = gmail.users().messages().list(
        userId=email,
        labelIds=label_ids,
        maxResults=max_results,
        q=query,
    ).execute()

    messages = response.get("messages", [])
    if not messages:
        return []

    # Fetch full message details
    full_messages = []
    for msg in messages:
        full_msg = gmail.users().messages().get(
            userId=email,
            id=msg["id"],
            format="full",
        ).execute()
        full_messages.append(full_msg)

    return full_messages


def extract_email_body(message: Dict[str, Any]) -> str:
    """Extract email body from Gmail message."""
    payload = message.get("payload", {})
    body = ""

    def extract_from_part(part: Dict[str, Any]) -> str:
        """Recursively extract text from message parts."""
        text = ""
        if part.get("mimeType") == "text/plain":
            data = part.get("body", {}).get("data")
            if data:
                try:
                    text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                except Exception:
                    pass
        elif part.get("mimeType") == "text/html" and not text:
            data = part.get("body", {}).get("data")
            if data:
                try:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    # Simple HTML stripping (for now)
                    import re
                    text = re.sub(r"<[^>]+>", "", html)
                except Exception:
                    pass

        # Check for nested parts
        if "parts" in part:
            for subpart in part.get("parts", []):
                subtext = extract_from_part(subpart)
                if subtext:
                    text = subtext if not text else text

        return text

    # Handle multipart messages
    if "parts" in payload:
        for part in payload.get("parts", []):
            text = extract_from_part(part)
            if text:
                body = text
                break
    else:
        # Single part message
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data")
            if data:
                try:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                except Exception:
                    pass

    return body or message.get("snippet", "")


def extract_headers(message: Dict[str, Any]) -> Dict[str, str]:
    """Extract email headers."""
    headers = message.get("payload", {}).get("headers", [])
    result = {}
    for header in headers:
        name = header.get("name", "").lower()
        value = header.get("value", "")
        result[name] = value
    return result


def check_existing_draft(
    creds: Credentials,
    email: str,
    thread_id: Optional[str],
) -> bool:
    """Check if a draft already exists for this thread."""
    if not thread_id:
        return False

    gmail = build("gmail", "v1", credentials=creds)
    try:
        drafts = gmail.users().drafts().list(
            userId=email,
            q=f"in:thread:{thread_id}",
        ).execute()
        return len(drafts.get("drafts", [])) > 0
    except Exception:
        return False


def draft_email_reply(
    llm: ChatGoogleGenerativeAI,
    original_email: Dict[str, Any],
    headers: Dict[str, str],
    body: str,
) -> str:
    """Use LangChain to draft an email reply."""
    subject = headers.get("subject", "No Subject")
    from_addr = headers.get("from", "Unknown")
    to_addr = headers.get("to", "")

    prompt = f"""You are a helpful email assistant. Draft a professional reply to the following email.

Original Email:
From: {from_addr}
To: {to_addr}
Subject: {subject}

Body:
{body[:1000]}

Draft a professional, concise reply that:
- Addresses the sender by name if available
- Responds to the key points in the email
- Maintains a professional tone
- Includes a polite closing

Provide only the email body text (no subject line, no headers)."""

    try:
        response = llm.invoke(prompt)
        reply = response.content if hasattr(response, "content") else str(response)
        return reply.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to generate reply: {str(e)}") from e


def create_gmail_draft(
    creds: Credentials,
    email: str,
    reply_body: str,
    original_subject: str,
    thread_id: Optional[str],
    reply_to_address: Optional[str] = None,
) -> str:
    """Create a Gmail draft."""
    gmail = build("gmail", "v1", credentials=creds)

    # Create MIME message
    from email.mime.text import MIMEText

    subject = f"Re: {original_subject}" if not original_subject.startswith("Re:") else original_subject

    message = MIMEText(reply_body)
    message["From"] = email
    message["To"] = reply_to_address or email
    message["Subject"] = subject

    if thread_id:
        message["In-Reply-To"] = f"<{thread_id}@mail.gmail.com>"
        message["References"] = f"<{thread_id}@mail.gmail.com>"

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    # Create draft
    draft_body = {"message": {"raw": raw_message}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    draft = gmail.users().drafts().create(userId=email, body=draft_body).execute()
    return draft["id"]


def get_credentials_for_email(email: str) -> Credentials:
    """
    Get Gmail API credentials for an email address.
    Uses Application Default Credentials or OAuth refresh tokens from environment.
    For now, supports simple OAuth refresh token via environment variable.
    """
    # Option 1: Use refresh token from environment variable (simple, no security for dev)
    refresh_token = os.environ.get(f"GMAIL_REFRESH_TOKEN_{email.replace('@', '_').replace('.', '_')}")
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    token_uri = os.environ.get("GMAIL_TOKEN_URI", "https://oauth2.googleapis.com/token")

    if refresh_token and client_id and client_secret:
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(google.auth.transport.requests.Request())
        return creds

    # Option 2: Try Application Default Credentials (for service accounts with domain-wide delegation)
    try:
        creds, project = google.auth.default(scopes=SCOPES)
        if isinstance(creds, Credentials):
            return creds
    except Exception:
        pass

    # If neither works, raise error
    raise NotImplementedError(
        f"Gmail API credentials not configured for {email}. "
        "Set environment variables: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
        f"and GMAIL_REFRESH_TOKEN_{email.replace('@', '_').replace('.', '_')}"
    )


@app.get("/", response_model=HealthResponse)
def root():
    """Root endpoint."""
    return HealthResponse(status="ok", message="Gmail Agent API is running")


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check endpoint."""
    return HealthResponse(status="ok", message="Healthy")


@app.post("/echo", response_model=EchoResponse)
def echo(request: EchoRequest):
    """Echo endpoint for testing."""
    return EchoResponse(echo=f"Echo: {request.message}", original=request.message)


@app.post("/agent/process-unread", response_model=ProcessUnreadResponse)
async def process_unread_emails(request: ProcessUnreadRequest) -> ProcessUnreadResponse:
    """
    Process unread emails and create draft replies using LangChain.
    """
    results: List[EmailProcessingResult] = []
    processed = 0
    succeeded = 0
    failed = 0

    try:
        # Get credentials
        creds = get_credentials_for_email(request.email)

        # Initialize LangChain model
        llm = get_llm()

        # Fetch unread messages
        print(f"Fetching unread emails for {request.email}...", flush=True)
        messages = fetch_unread_messages(
            creds,
            request.email,
            max_results=request.max_emails,
            label_ids=request.label_ids,
        )

        total_found = len(messages)
        print(f"Found {total_found} unread email(s)", flush=True)

        # Process each message
        for msg in messages:
            message_id = msg.get("id")
            thread_id = msg.get("threadId")
            headers = extract_headers(msg)
            subject = headers.get("subject", "No Subject")
            from_addr = headers.get("from", "Unknown")

            # Skip if draft already exists
            if request.skip_existing_drafts and check_existing_draft(creds, request.email, thread_id):
                print(f"Skipping {message_id} - draft already exists", flush=True)
                results.append(
                    EmailProcessingResult(
                        message_id=message_id,
                        subject=subject,
                        from_address=from_addr,
                        success=False,
                        error="Draft already exists",
                    )
                )
                continue

            try:
                print(f"Processing message {message_id}: {subject}", flush=True)

                # Extract email body
                body = extract_email_body(msg)

                # Draft reply using LangChain
                reply = draft_email_reply(llm, msg, headers, body)

                # Get reply-to address (usually the "from" address of original)
                reply_to = from_addr.split("<")[-1].split(">")[0].strip() if "<" in from_addr else from_addr

                # Create draft
                draft_id = create_gmail_draft(
                    creds,
                    request.email,
                    reply,
                    subject,
                    thread_id,
                    reply_to_address=reply_to,
                )

                print(f"Created draft {draft_id} for message {message_id}", flush=True)

                results.append(
                    EmailProcessingResult(
                        message_id=message_id,
                        subject=subject,
                        from_address=from_addr,
                        success=True,
                        draft_id=draft_id,
                    )
                )

                processed += 1
                succeeded += 1

            except Exception as e:
                error_msg = str(e)
                print(f"Error processing {message_id}: {error_msg}", flush=True)

                results.append(
                    EmailProcessingResult(
                        message_id=message_id,
                        subject=subject,
                        from_address=from_addr,
                        success=False,
                        error=error_msg,
                    )
                )

                processed += 1
                failed += 1
                continue

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process unread emails: {str(e)}",
        ) from e

    return ProcessUnreadResponse(
        email=request.email,
        total_found=total_found,
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
