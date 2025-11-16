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
from fastapi import Header
from google.cloud import aiplatform
from google.cloud import secretmanager
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
import vertexai
from vertexai.language_models import TextEmbeddingModel

app = FastAPI(title="Gmail Agent API", version="0.1.0")

# Configuration
PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("LOCATION", "us-central1")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
REFRESH_TOKEN_SECRET_NAME = os.environ.get("REFRESH_TOKEN_SECRET_NAME", "gmail-refresh-tokens")
OAUTH_CLIENT_SECRET_NAME = os.environ.get("OAUTH_CLIENT_SECRET_NAME")  # e.g., gmail-oauth-client

# RAG Configuration (optional)
VERTEX_INDEX_ENDPOINT = os.environ.get("VERTEX_INDEX_ENDPOINT")
VERTEX_DEPLOYED_INDEX_ID = os.environ.get("VERTEX_DEPLOYED_INDEX_ID")
VERTEX_EMBEDDING_MODEL = os.environ.get("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
RAG_ENABLED = bool(VERTEX_INDEX_ENDPOINT and VERTEX_DEPLOYED_INDEX_ID)

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


class PubSubMessage(BaseModel):
    message: Dict[str, Any]
    subscription: Optional[str] = None

# Initialize LangChain model
_llm = None

# Initialize Vertex AI for RAG
_vertex_initialized = False
_embedding_model = None
_secret_client: secretmanager.SecretManagerServiceClient | None = None


def get_secret_client() -> secretmanager.SecretManagerServiceClient:
    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()
    return _secret_client


def _iter_refresh_token_entries() -> List[Dict[str, Any]]:
    if not PROJECT_ID:
        raise RuntimeError("PROJECT_ID must be set to read secrets")
    client = get_secret_client()
    entries: List[Dict[str, Any]] = []
    # First, try accessing 'latest' directly (works with roles/secretmanager.secretAccessor)
    latest_name = f"projects/{PROJECT_ID}/secrets/{REFRESH_TOKEN_SECRET_NAME}/versions/latest"
    try:
        resp = client.access_secret_version(name=latest_name)
        payload = resp.payload.data.decode("utf-8")
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                entries.append(parsed)
                return entries
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        entries.append(item)
                return entries
        except Exception:
            pass
    except Exception as e:
        # Log and fall back to listing (if permitted)
        print(f"_iter_refresh_token_entries: access latest failed: {type(e).__name__}: {str(e)}", flush=True)
    # Fallback: list versions (requires additional list permissions)
    parent = f"projects/{PROJECT_ID}/secrets/{REFRESH_TOKEN_SECRET_NAME}"
    try:
        for version in client.list_secret_versions(request={"parent": parent}):
            if getattr(version, "state", None) and getattr(version.state, "name", "") != "ENABLED":
                continue
            try:
                resp = client.access_secret_version(name=version.name)
                parsed = json.loads(resp.payload.data.decode("utf-8"))
                if isinstance(parsed, dict):
                    entries.append(parsed)
                elif isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict):
                            entries.append(item)
            except Exception as inner:
                print(f"_iter_refresh_token_entries: skip version due to error: {type(inner).__name__}: {str(inner)}", flush=True)
                continue
    except Exception as e:
        print(f"_iter_refresh_token_entries: list versions failed: {type(e).__name__}: {str(e)}", flush=True)
    return entries


def _get_refresh_token_from_secret(email: str) -> Optional[str]:
    tokens = _iter_refresh_token_entries()
    for entry in tokens:
        if entry.get("email") == email:
            return entry.get("refresh_token")
    return None


def _load_oauth_client_from_secret() -> Optional[Dict[str, Any]]:
    """
    Load OAuth client JSON from Secret Manager when OAUTH_CLIENT_SECRET_NAME is set.
    Supports both 'installed' and 'web' formats; returns the nested dict.
    """
    if not OAUTH_CLIENT_SECRET_NAME or not PROJECT_ID:
        return None
    name = f"projects/{PROJECT_ID}/secrets/{OAUTH_CLIENT_SECRET_NAME}/versions/latest"
    try:
        client = get_secret_client()
        resp = client.access_secret_version(name=name)
        data = json.loads(resp.payload.data.decode("utf-8"))
        if "installed" in data and isinstance(data["installed"], dict):
            return data["installed"]
        if "web" in data and isinstance(data["web"], dict):
            return data["web"]
        # If it's already the inner object
        return data if isinstance(data, dict) else None
    except Exception:
        return None


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


def _ensure_vertex_init():
    """Initialize Vertex AI for RAG if enabled."""
    global _vertex_initialized, _embedding_model
    if not RAG_ENABLED:
        return None
    
    if not _vertex_initialized:
        if not PROJECT_ID:
            raise RuntimeError("PROJECT_ID environment variable must be set for RAG")
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        aiplatform.init(project=PROJECT_ID, location=LOCATION)
        _embedding_model = TextEmbeddingModel.from_pretrained(VERTEX_EMBEDDING_MODEL)
        _vertex_initialized = True
        print(f"Initialized Vertex AI RAG: endpoint={VERTEX_INDEX_ENDPOINT}, index={VERTEX_DEPLOYED_INDEX_ID}", flush=True)
    return _embedding_model


def retrieve_context(query_text: str) -> List[Dict[str, Any]]:
    """
    Retrieve relevant context from Vertex Matching Engine using RAG.
    Returns a list of relevant document chunks.
    """
    if not RAG_ENABLED:
        return []
    
    try:
        embedding_model = _ensure_vertex_init()
        if not embedding_model:
            return []
        
        # Generate embedding for the query
        vector = embedding_model.get_embeddings([query_text])[0].values
        
        # Query the Matching Engine endpoint
        endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=VERTEX_INDEX_ENDPOINT)
        response = endpoint.find_neighbors(
            deployed_index_id=VERTEX_DEPLOYED_INDEX_ID,
            queries=[vector],
            num_neighbors=5,  # Retrieve top 5 similar chunks
        )
        
        neighbors = response[0].neighbors if response else []
        results: List[Dict[str, Any]] = []
        for n in neighbors:
            # Extract text from datapoint (stored during ingestion)
            # Note: The actual text might be in metadata or we need to fetch it
            results.append(
                {
                    "id": n.id,
                    "distance": n.distance,
                    # Note: Metadata retrieval depends on how it was stored during ingestion
                    # For now, we'll just store the IDs and distances
                }
            )
        
        print(f"Retrieved {len(results)} relevant chunks from RAG", flush=True)
        return results
    
    except Exception as e:
        print(f"Error retrieving RAG context: {str(e)}", flush=True)
        # Don't fail the entire request if RAG fails
        return []


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
    rag_context: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Use LangChain to draft an email reply, optionally using RAG context."""
    subject = headers.get("subject", "No Subject")
    from_addr = headers.get("from", "Unknown")
    to_addr = headers.get("to", "")

    # Build context section if RAG results are available
    context_section = ""
    if rag_context and len(rag_context) > 0:
        context_section = "\n\nRelevant Knowledge Base Context:\n"
        # Note: Full text retrieval from datapoints requires fetching from storage
        # For now, we'll indicate that context was retrieved with relevance scores
        for idx, doc in enumerate(rag_context[:5], start=1):
            relevance = 1 - doc.get("distance", 1.0)  # Convert distance to relevance (lower distance = higher relevance)
            context_section += f"[Context {idx}] Relevance: {relevance:.2f}\n"
        context_section += "\nUse this context to provide accurate, informed responses when relevant.\n"
    else:
        context_section = ""

    prompt = f"""You are a helpful email assistant. Draft a professional reply to the following email.

Original Email:
From: {from_addr}
To: {to_addr}
Subject: {subject}

Body:
{body[:1000]}{context_section}

Draft a professional, concise reply that:
- Addresses the sender by name if available
- Responds to the key points in the email
- Uses the provided context when relevant to answer questions or provide accurate information
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
    original_message_id: Optional[str] = None,
) -> str:
    """Create a Gmail draft."""
    gmail = build("gmail", "v1", credentials=creds)

    # Create MIME message
    from email.mime.text import MIMEText
    from email.utils import formataddr, make_msgid

    subject = f"Re: {original_subject}" if not original_subject.startswith("Re:") else original_subject

    # Ensure reply_body is not empty
    if not reply_body or not reply_body.strip():
        raise ValueError("Reply body cannot be empty")

    message = MIMEText(reply_body, _charset="utf-8")
    message["From"] = email
    message["To"] = reply_to_address or email
    message["Subject"] = subject

    # Properly set In-Reply-To and References for threading
    # Gmail will handle threading if we set threadId, but proper headers help
    if original_message_id:
        # Use the original message's Message-ID if available
        # Format: <message-id> where message-id is the actual Message-ID header
        message["In-Reply-To"] = original_message_id
        message["References"] = original_message_id

    # Create draft with threadId for proper threading
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    
    # Debug: Log message details (without exposing sensitive content)
    print(f"Creating draft: subject='{subject}', to='{reply_to_address}', body_length={len(reply_body)}, thread_id={thread_id}", flush=True)

    draft_body = {"message": {"raw": raw_message}}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    draft = gmail.users().drafts().create(userId=email, body=draft_body).execute()
    return draft["id"]


def get_credentials_for_email(email: str) -> Credentials:
    """
    Get Gmail API credentials for an email address.
    Prefers OAuth refresh tokens stored in Secret Manager (REFRESH_TOKEN_SECRET_NAME).
    Falls back to environment variables for development.
    """
    # Option 1: Secret Manager
    refresh_token = _get_refresh_token_from_secret(email)
    # Load client credentials from Secret Manager (preferred) or env
    client_json = _load_oauth_client_from_secret()
    client_id = (client_json or {}).get("client_id") or os.environ.get("GMAIL_CLIENT_ID")
    client_secret = (client_json or {}).get("client_secret") or os.environ.get("GMAIL_CLIENT_SECRET")
    token_uri = (client_json or {}).get("token_uri") or os.environ.get("GMAIL_TOKEN_URI", "https://oauth2.googleapis.com/token")
    print(f"get_credentials_for_email: client_json_loaded={bool(client_json)} token_from_secret={bool(refresh_token)}", flush=True)

    if refresh_token and client_id and client_secret:
        print("get_credentials_for_email: building Credentials from Secret Manager token", flush=True)
        creds = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        try:
            creds.refresh(google.auth.transport.requests.Request())
            print("get_credentials_for_email: refreshed access token using secret refresh_token", flush=True)
        except Exception as e:
            print(f"get_credentials_for_email: ERROR refreshing token from secret: {type(e).__name__}: {str(e)}", flush=True)
        return creds

    # Option 2: Use refresh token from environment variable (simple, dev)
    refresh_token_env = os.environ.get(f"GMAIL_REFRESH_TOKEN_{email.replace('@', '_').replace('.', '_')}")
    if refresh_token_env and client_id and client_secret:
        print("get_credentials_for_email: building Credentials from env refresh token", flush=True)
        creds = Credentials(
            None,
            refresh_token=refresh_token_env,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        try:
            creds.refresh(google.auth.transport.requests.Request())
            print("get_credentials_for_email: refreshed access token using env refresh token", flush=True)
        except Exception as e:
            print(f"get_credentials_for_email: ERROR refreshing token from env: {type(e).__name__}: {str(e)}", flush=True)
        return creds

    # Option 3: Try Application Default Credentials (for service accounts with domain-wide delegation)
    try:
        creds, project = google.auth.default(scopes=SCOPES)
        if isinstance(creds, Credentials):
            print("get_credentials_for_email: using Application Default Credentials", flush=True)
            return creds
    except Exception:
        pass

    # If neither works, raise error
    missing_parts: List[str] = []
    if not client_id or not client_secret:
        missing_parts.append("OAuth client (client_id/client_secret)")
    if not refresh_token and not os.environ.get(f"GMAIL_REFRESH_TOKEN_{email.replace('@', '_').replace('.', '_')}"):
        missing_parts.append("refresh token (Secret Manager entry or per-email env)")
    detail = (
        f"Gmail API credentials not configured for {email}. Missing: {', '.join(missing_parts)}. "
        f"Expected either Secret Manager '{REFRESH_TOKEN_SECRET_NAME}' with "
        f"{{\"email\":\"{email}\",\"refresh_token\":\"...\"}} and OAuth client via "
        f"OAUTH_CLIENT_SECRET_NAME='{OAUTH_CLIENT_SECRET_NAME or ''}', "
        f"or per-email env GMAIL_REFRESH_TOKEN_{email.replace('@', '_').replace('.', '_')}."
    )
    raise NotImplementedError(detail)


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


def _fetch_message_by_hint(
    creds: Credentials,
    email: str,
    message_id: Optional[str],
    history_id: Optional[str],
) -> Dict[str, Any]:
    gmail = build("gmail", "v1", credentials=creds)
    if message_id:
        return gmail.users().messages().get(userId=email, id=message_id, format="full").execute()
    if not history_id:
        raise ValueError("historyId is required when messageId is missing")
    history = gmail.users().history().list(userId=email, startHistoryId=history_id, historyTypes=["MESSAGE_ADDED"]).execute()
    histories = history.get("history", [])
    for entry in histories:
        for added in entry.get("messagesAdded", []):
            return gmail.users().messages().get(userId=email, id=added["message"]["id"], format="full").execute()
    raise RuntimeError("No recent messages found for provided historyId")


@app.post("/pubsub/push")
async def handle_pubsub_push(body: PubSubMessage, authorization: Optional[str] = Header(default=None)) -> Dict[str, str]:
    """
    Minimal Pub/Sub push handler for Gmail watch notifications.
    Note: For simplicity, token verification is not implemented here.
    """
    attributes = body.message.get("attributes", {})
    envelope_data = body.message.get("data")
    print(f"/pubsub/push: received message with attributes keys={list(attributes.keys()) if isinstance(attributes, dict) else type(attributes)}", flush=True)
    if envelope_data:
        print(f"/pubsub/push: envelope_data length={len(envelope_data)} (base64)", flush=True)
    if not envelope_data:
        raise HTTPException(status_code=400, detail="Missing message data")
    try:
        decoded_json = base64.b64decode(envelope_data).decode("utf-8")
        print(f"/pubsub/push: decoded JSON (truncated 200 chars)={decoded_json[:200]}", flush=True)
        decoded = json.loads(decoded_json)
    except Exception:
        print("/pubsub/push: failed to decode Pub/Sub data as JSON", flush=True)
        raise HTTPException(status_code=400, detail="Invalid message data")

    email_address = decoded.get("emailAddress")
    message_id = decoded.get("messageId")
    history_id = decoded.get("historyId")

    if not email_address:
        raise HTTPException(status_code=400, detail="Missing email address in notification")

    try:
        # Resolve credentials for this email
        print(f"/pubsub/push: resolving credentials for email={email_address}", flush=True)
        creds = get_credentials_for_email(email_address)
        print(f"/pubsub/push: credentials resolved for {email_address}", flush=True)

        # Initialize LangChain model
        llm = get_llm()
        print("/pubsub/push: LLM initialized", flush=True)

        # Fetch message
        print(f"/pubsub/push: fetching message (messageId={message_id}, historyId={history_id})", flush=True)
        message = _fetch_message_by_hint(creds, email_address, message_id, history_id)
        print(f"/pubsub/push: fetched message id={message.get('id')} threadId={message.get('threadId')}", flush=True)
        headers = extract_headers(message)
        subject = headers.get("subject", "No Subject")
        from_addr = headers.get("from", "Unknown")
        body_text = extract_email_body(message)
        print(f"/pubsub/push: extracted headers subject='{subject}' from='{from_addr}' body_len={len(body_text)}", flush=True)

        # Retrieve RAG context (optional)
        rag_context = None
        if RAG_ENABLED:
            query_text = f"{subject} {body_text[:500]}"
            print("/pubsub/push: retrieving RAG context...", flush=True)
            rag_context = retrieve_context(query_text)
            print(f"/pubsub/push: RAG results count={len(rag_context) if rag_context else 0}", flush=True)

        # Draft reply
        print("/pubsub/push: drafting reply...", flush=True)
        reply = draft_email_reply(llm, message, headers, body_text, rag_context=rag_context)
        print(f"/pubsub/push: draft generated length={len(reply)}", flush=True)

        # Create draft
        thread_id = message.get("threadId")
        reply_to = from_addr.split("<")[-1].split(">")[0].strip() if "<" in from_addr else from_addr
        original_message_id = headers.get("message-id") or (f"<{message_id}@mail.gmail.com>" if message_id else None)
        print(f"/pubsub/push: creating Gmail draft to='{reply_to}' threadId={thread_id} has_msgid={bool(original_message_id)}", flush=True)
        draft_id = create_gmail_draft(
            creds,
            email_address,
            reply,
            subject,
            thread_id,
            reply_to_address=reply_to,
            original_message_id=original_message_id,
        )

        print(f"Created draft {draft_id} for email {email_address} (messageId={message_id}, historyId={history_id})", flush=True)
        return {"status": "ok", "draft_id": draft_id}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"/pubsub/push: ERROR {type(e).__name__}: {str(e)}", flush=True)
        print(tb, flush=True)
        raise HTTPException(status_code=500, detail=f"Failed to process notification: {str(e)}") from e


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

                # Retrieve RAG context (if enabled)
                rag_context = None
                if RAG_ENABLED:
                    query_text = f"{subject} {body[:500]}"
                    rag_context = retrieve_context(query_text)
                    if rag_context:
                        print(f"Retrieved {len(rag_context)} relevant chunks from RAG for {message_id}", flush=True)

                # Draft reply using LangChain with RAG context
                reply = draft_email_reply(llm, msg, headers, body, rag_context=rag_context)
                print(f"Generated reply for {message_id} (length: {len(reply)} chars): {reply[:200]}...", flush=True)

                # Get reply-to address (usually the "from" address of original)
                reply_to = from_addr.split("<")[-1].split(">")[0].strip() if "<" in from_addr else from_addr

                # Get original message ID for proper threading
                original_message_id = headers.get("message-id") or f"<{message_id}@mail.gmail.com>"

                # Create draft
                draft_id = create_gmail_draft(
                    creds,
                    request.email,
                    reply,
                    subject,
                    thread_id,
                    reply_to_address=reply_to,
                    original_message_id=original_message_id,
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
