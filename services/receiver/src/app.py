"""
FastAPI application that handles Pub/Sub push notifications, Gmail OAuth flow,
and directly triggers the Vertex ADK agent to draft replies.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from typing import Any, Dict, List, Optional

import google.auth.transport.requests
import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from google.auth import jwt
from google.auth.exceptions import GoogleAuthError
from google_auth_oauthlib.flow import Flow
from google.cloud import secretmanager
from google.oauth2 import credentials
from googleapiclient.discovery import build
from pydantic import BaseModel

PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("REGION", "us-central1")
PUBSUB_VERIFICATION_AUDIENCE = os.environ.get("PUBSUB_VERIFICATION_AUDIENCE")
AGENT_ENDPOINT = os.environ.get("AGENT_ENDPOINT")
OAUTH_CLIENT_SECRET_NAME = os.environ.get(
    "OAUTH_CLIENT_SECRET_NAME", f"projects/{PROJECT_ID}/secrets/gmail-oauth-client/versions/latest"
)
REFRESH_TOKEN_SECRET_NAME = os.environ.get(
    "REFRESH_TOKEN_SECRET_NAME", f"projects/{PROJECT_ID}/secrets/gmail-refresh-tokens"
)

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

app = FastAPI(title="Gmail Receiver Service", version="0.1.0")
secret_client = secretmanager.SecretManagerServiceClient()


class PubSubMessage(BaseModel):
    message: Dict[str, Any]
    subscription: str


def load_oauth_config() -> Dict[str, Any]:
    response = secret_client.access_secret_version(name=OAUTH_CLIENT_SECRET_NAME)
    return json.loads(response.payload.data.decode("utf-8"))


def verify_pubsub_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token in Authorization header"
        )

    if not PUBSUB_VERIFICATION_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PUBSUB_VERIFICATION_AUDIENCE environment variable not set. Please redeploy the service."
        )

    token = authorization.split(" ", 1)[1]
    
    try:
        # For Pub/Sub push notifications with OIDC tokens, verify the JWT
        # Pub/Sub signs the JWT with Google's OIDC service (service account)
        # Fetch certificates from Google's OAuth2 certificate endpoint
        certs_url = "https://www.googleapis.com/oauth2/v1/certs"
        
        # Fetch certificates using httpx
        with httpx.Client() as client:
            certs_response = client.get(certs_url, timeout=10.0)
            certs_response.raise_for_status()
            certs = certs_response.json()
        
        # jwt.decode() from google.auth.jwt expects:
        # - token: JWT token string (first positional argument)
        # - certs: dict mapping key IDs (kid) to PEM certificate strings (second positional argument)
        # - audience: expected audience claim (keyword argument)
        # The library will automatically find the correct certificate based on the 'kid' in the JWT header
        decoded_token = jwt.decode(
            token,
            certs,
            audience=PUBSUB_VERIFICATION_AUDIENCE
        )
        
    except Exception as exc:
        # Log detailed error for debugging
        error_type = type(exc).__name__
        error_msg = str(exc)
        print(f"JWT verification failed: {error_type}: {error_msg}", flush=True)
        print(f"Audience being checked: {PUBSUB_VERIFICATION_AUDIENCE}", flush=True)
        print(f"Token length: {len(token)}", flush=True)
        
        # Check if it's an audience mismatch
        if "audience" in error_msg.lower() or "aud" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token audience mismatch. Expected: {PUBSUB_VERIFICATION_AUDIENCE}"
            ) from exc
        
        # Check if it's a signature error
        if "signature" in error_msg.lower() or "certificate" in error_msg.lower() or "invalid" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token signature verification failed: {error_msg}"
            ) from exc
        
        # Generic error
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid Pub/Sub token: {error_type}: {error_msg}"
        ) from exc


def iter_refresh_tokens() -> List[Dict[str, Any]]:
    tokens: List[Dict[str, Any]] = []
    for version in secret_client.list_secret_versions(request={"parent": REFRESH_TOKEN_SECRET_NAME}):
        if version.state.name != "ENABLED":
            continue
        response = secret_client.access_secret_version(name=version.name)
        try:
            tokens.append(json.loads(response.payload.data.decode("utf-8")))
        except json.JSONDecodeError:
            continue
    return tokens


def get_refresh_token(email: str) -> str:
    for entry in iter_refresh_tokens():
        if entry.get("email") == email:
            return entry["refresh_token"]
    raise RuntimeError(f"No refresh token stored for {email}")


def build_credentials(email: str) -> credentials.Credentials:
    oauth_config = load_oauth_config()
    refresh_token = get_refresh_token(email)
    creds = credentials.Credentials(
        None,
        refresh_token=refresh_token,
        token_uri=oauth_config["web"]["token_uri"],
        client_id=oauth_config["web"]["client_id"],
        client_secret=oauth_config["web"]["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds


def fetch_message(creds: credentials.Credentials, email: str, message_id_hint: Optional[str], history_id: Optional[str]) -> Dict[str, Any]:
    gmail = build("gmail", "v1", credentials=creds)
    if message_id_hint:
        return gmail.users().messages().get(userId=email, id=message_id_hint, format="full").execute()

    if not history_id:
        raise ValueError("historyId required when messageId missing")

    history = gmail.users().history().list(userId=email, startHistoryId=history_id, historyTypes=["MESSAGE_ADDED"]).execute()
    histories = history.get("history", [])
    for entry in histories:
        for message in entry.get("messagesAdded", []):
            return gmail.users().messages().get(userId=email, id=message["message"]["id"], format="full").execute()
    raise RuntimeError("No recent messages found for provided historyId")


def sanitize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    headers = message.get("payload", {}).get("headers", [])
    def header(name: str) -> str:
        return next((h["value"] for h in headers if h["name"].lower() == name.lower()), "")

    return {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "snippet": message.get("snippet", ""),
        "subject": header("Subject"),
        "from": header("From"),
        "to": header("To"),
        "labelIds": message.get("labelIds", []),
    }


def call_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not AGENT_ENDPOINT:
        raise RuntimeError("AGENT_ENDPOINT must be configured")
    with httpx.Client(timeout=30.0) as client:
        response = client.post(AGENT_ENDPOINT, json=payload)
        response.raise_for_status()
        return response.json()


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/pubsub/push", status_code=status.HTTP_204_NO_CONTENT)
async def handle_pubsub_push(body: PubSubMessage, authorization: Optional[str] = Header(default=None)) -> Response:
    verify_pubsub_token(authorization)

    attributes = body.message.get("attributes", {})
    envelope_data = body.message.get("data")
    if not envelope_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing message data")

    decoded = json.loads(base64.b64decode(envelope_data).decode("utf-8"))
    message_id = decoded.get("messageId")
    history_id = decoded.get("historyId")
    email_address = decoded.get("emailAddress")

    if not email_address:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing email address in notification")

    try:
        creds = build_credentials(email_address)
        message = fetch_message(creds, email_address, message_id, history_id)
        sanitized = sanitize_message(message)

        agent_response = call_agent(
            {
                "gmail_user": email_address,
                "message": sanitized,
                "original_message_id": message.get("id"),
                "pubsub_attributes": attributes,
            }
        )
        print(json.dumps({"agent_response": agent_response}))  # basic structured logging
    except Exception as exc:  # broad catch to force Pub/Sub retry on failure
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/oauth/start")
def oauth_start(request: Request) -> Response:
    oauth_config = load_oauth_config()

    redirect_uri = str(request.url_for("oauth_callback"))
    state = secrets.token_urlsafe(32)

    flow = Flow.from_client_config(
        oauth_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    response = Response(status_code=status.HTTP_302_FOUND)
    response.headers["Location"] = authorization_url
    response.set_cookie("oauth_state", state, secure=True, httponly=True, max_age=300)
    return response


@app.get("/oauth/callback")
def oauth_callback(request: Request, state: str, code: str) -> Dict[str, str]:
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State mismatch")

    oauth_config = load_oauth_config()
    redirect_uri = str(request.url_for("oauth_callback"))
    flow = Flow.from_client_config(
        oauth_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(code=code)

    creds = flow.credentials
    user_info = fetch_user_profile(creds)

    store_refresh_token(user_info["email"], creds.refresh_token)
    register_watch(creds, user_info["email"])

    return {
        "status": "success",
        "message": f"Registered watch for {user_info['email']}",
    }


def fetch_user_profile(creds: credentials.Credentials) -> Dict[str, Any]:
    service = build("oauth2", "v2", credentials=creds)
    userinfo = service.userinfo().get().execute()
    return userinfo


def store_refresh_token(email: str, refresh_token: str) -> None:
    payload = json.dumps({"email": email, "refresh_token": refresh_token}).encode("utf-8")
    secret_client.add_secret_version(parent=REFRESH_TOKEN_SECRET_NAME, payload={"data": payload})


def register_watch(creds: credentials.Credentials, email: str) -> None:
    gmail_service = build("gmail", "v1", credentials=creds)
    request_body = {
        "topicName": f"projects/{PROJECT_ID}/topics/gmail-notifications",
        "labelIds": ["INBOX"],
    }
    gmail_service.users().watch(userId=email, body=request_body).execute()


@app.post("/watch")
def manual_watch(body: Dict[str, str]) -> Dict[str, str]:
    """Manual re-registration endpoint; expects {"email": "..."} payload."""
    email = body.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing email")

    refresh_token = get_refresh_token(email)

    oauth_config = load_oauth_config()
    creds = credentials.Credentials(
        None,
        refresh_token=refresh_token,
        token_uri=oauth_config["web"]["token_uri"],
        client_id=oauth_config["web"]["client_id"],
        client_secret=oauth_config["web"]["client_secret"],
        scopes=SCOPES,
    )
    creds.refresh(google.auth.transport.requests.Request())
    register_watch(creds, email)
    return {"status": "re-registered", "email": email}



