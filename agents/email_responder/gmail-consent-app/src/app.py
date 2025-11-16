"""
Minimal local consent app.
Starts OAuth flow for a given OAuth client, captures refresh token on callback,
and stores it in Secret Manager in the configured GCP project.
"""
from __future__ import annotations

import json
import os
import secrets
from typing import Any, Dict

import google.auth.transport.requests
from fastapi import FastAPI, HTTPException, Request, Response, status
from google.cloud import secretmanager
from google_auth_oauthlib.flow import Flow
from google.oauth2 import credentials
from googleapiclient.discovery import build

PROJECT_ID = os.environ.get("PROJECT_ID")
OAUTH_CLIENT_FILE = os.environ.get("OAUTH_CLIENT_FILE", "oauth-client.json")
OAUTH_CLIENT_SECRET_NAME = os.environ.get("OAUTH_CLIENT_SECRET_NAME", "gmail-oauth-client")
REFRESH_TOKEN_SECRET_NAME = os.environ.get("REFRESH_TOKEN_SECRET_NAME", "gmail-refresh-tokens")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

app = FastAPI(title="Local Gmail Consent App", version="0.1.0")
_secret_client: secretmanager.SecretManagerServiceClient | None = None

def get_secret_client() -> secretmanager.SecretManagerServiceClient:
    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()
    return _secret_client

def load_oauth_client_config_from_file() -> Dict[str, Any]:
    if not os.path.exists(OAUTH_CLIENT_FILE):
        raise FileNotFoundError(f"OAuth client file not found: {OAUTH_CLIENT_FILE}")
    with open(OAUTH_CLIENT_FILE, "r", encoding="utf-8") as f:
        return json.loads(f.read())

def ensure_secret_exists(project_id: str, secret_id: str) -> None:
    client = get_secret_client()
    parent = f"projects/{project_id}"
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        print(f"Created secret: {secret_id}", flush=True)
    except Exception as exc:
        # If it already exists, ignore; else re-raise
        msg = str(exc)
        if "AlreadyExists" in msg or "409" in msg:
            return
        raise

def store_refresh_token(email: str, refresh_token: str) -> None:
    if not PROJECT_ID:
        raise RuntimeError("PROJECT_ID must be set to store secrets")
    ensure_secret_exists(PROJECT_ID, REFRESH_TOKEN_SECRET_NAME)
    client = get_secret_client()
    parent = f"projects/{PROJECT_ID}/secrets/{REFRESH_TOKEN_SECRET_NAME}"
    payload = json.dumps({"email": email, "refresh_token": refresh_token}).encode("utf-8")
    client.add_secret_version(request={"parent": parent, "payload": {"data": payload}})
    print(f"Stored refresh token for {email} in secret {REFRESH_TOKEN_SECRET_NAME}", flush=True)

@app.get("/")
def root() -> Dict[str, str]:
    return {
        "service": "Local Gmail Consent App",
        "oauth_start": "/oauth/start",
        "health": "/healthz",
    }

@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}

@app.get("/oauth/start")
def oauth_start(request: Request) -> Response:
    # Load client config from local file
    oauth_config = load_oauth_client_config_from_file()
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
    response.set_cookie("oauth_state", state, secure=False, httponly=True, max_age=300)
    return response

@app.get("/oauth/callback")
def oauth_callback(request: Request, state: str, code: str) -> Dict[str, str]:
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State mismatch")

    oauth_config = load_oauth_client_config_from_file()
    redirect_uri = str(request.url_for("oauth_callback"))
    flow = Flow.from_client_config(
        oauth_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    flow.fetch_token(code=code)

    creds: credentials.Credentials = flow.credentials
    # Force an access token to verify validity
    creds.refresh(google.auth.transport.requests.Request())

    # Fetch the user's email
    oauth2 = build("oauth2", "v2", credentials=creds)
    userinfo = oauth2.userinfo().get().execute()
    email = userinfo.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to fetch user email")

    if not creds.refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No refresh token returned (try prompt=consent)")

    store_refresh_token(email, creds.refresh_token)
    return {
        "status": "success",
        "email": email,
        "message": f"Stored refresh token in Secret Manager secret '{REFRESH_TOKEN_SECRET_NAME}' in project '{PROJECT_ID}'",
    }