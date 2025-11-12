"""
Vertex ADK-compatible agent service that performs RAG and creates Gmail drafts.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import google.auth.transport.requests
from fastapi import FastAPI, HTTPException, Request, Response, status
from google.cloud import aiplatform, secretmanager
from google.oauth2 import credentials
from googleapiclient.discovery import build
from pydantic import BaseModel
import vertexai
from vertexai.language_models import TextEmbeddingModel
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig

PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("LOCATION", "us-central1")
VERTEX_INDEX_ENDPOINT = os.environ.get("VERTEX_INDEX_ENDPOINT")
VERTEX_DEPLOYED_INDEX_ID = os.environ.get("VERTEX_DEPLOYED_INDEX_ID")
VERTEX_EMBEDDING_MODEL = os.environ.get("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
VERTEX_GENERATION_MODEL = os.environ.get("VERTEX_GENERATION_MODEL", "gemini-1.5-flash")
REFRESH_TOKEN_SECRET_NAME = os.environ.get(
    "REFRESH_TOKEN_SECRET_NAME", f"projects/{PROJECT_ID}/secrets/gmail-refresh-tokens"
)
OAUTH_CLIENT_SECRET_NAME = os.environ.get(
    "OAUTH_CLIENT_SECRET_NAME", f"projects/{PROJECT_ID}/secrets/gmail-oauth-client/versions/latest"
)
GMAIL_DRAFT_LABEL = os.environ.get("GMAIL_DRAFT_LABEL", "auto-draft://pending-review")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]

vertexai.init(project=PROJECT_ID, location=LOCATION)
aiplatform.init(project=PROJECT_ID, location=LOCATION)

app = FastAPI(title="Vertex ADK Agent", version="0.1.0")
secret_client = secretmanager.SecretManagerServiceClient()
embedding_model = TextEmbeddingModel.from_pretrained(VERTEX_EMBEDDING_MODEL)
generative_model = GenerativeModel(VERTEX_GENERATION_MODEL)


class AgentRequest(BaseModel):
    gmail_user: str
    message: Dict[str, Any]
    original_message_id: str


class AgentResponse(BaseModel):
    draft_id: str
    summary: str
    retrieved_docs: List[Dict[str, Any]]


def load_oauth_config() -> Dict[str, Any]:
    response = secret_client.access_secret_version(name=OAUTH_CLIENT_SECRET_NAME)
    return json.loads(response.payload.data.decode("utf-8"))


def iter_refresh_tokens() -> List[Dict[str, Any]]:
    tokens: List[Dict[str, Any]] = []
    for version in secret_client.list_secret_versions(request={"parent": REFRESH_TOKEN_SECRET_NAME}):
        if version.state.name != "ENABLED":
            continue
        resp = secret_client.access_secret_version(name=version.name)
        try:
            tokens.append(json.loads(resp.payload.data.decode("utf-8")))
        except json.JSONDecodeError:
            continue
    return tokens


def get_refresh_token(email: str) -> str:
    for entry in iter_refresh_tokens():
        if entry.get("email") == email:
            return entry["refresh_token"]
    raise RuntimeError(f"No refresh token for {email}")


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


def retrieve_context(query_text: str) -> List[Dict[str, Any]]:
    if not (VERTEX_INDEX_ENDPOINT and VERTEX_DEPLOYED_INDEX_ID):
        return []
    vector = embedding_model.get_embeddings([query_text])[0].values

    endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=VERTEX_INDEX_ENDPOINT)
    response = endpoint.find_neighbors(
        deployed_index_id=VERTEX_DEPLOYED_INDEX_ID,
        queries=[vector],
        num_neighbors=5,
    )
    neighbors = response[0].neighbors if response else []
    results: List[Dict[str, Any]] = []
    for n in neighbors:
        results.append(
            {
                "id": n.id,
                "distance": n.distance,
                "metadata": json.loads(n.metadata) if n.metadata else {},
            }
        )
    return results


def build_prompt(email_snippet: Dict[str, Any], retrieved: List[Dict[str, Any]]) -> str:
    provenance_lines = []
    for idx, doc in enumerate(retrieved, start=1):
        text = doc.get("metadata", {}).get("chunk", "")
        provenance_lines.append(f"[{idx}] {text}")

    provenance_block = "\n".join(provenance_lines) if provenance_lines else "No additional context."
    return f"""
You are an assistant drafting Gmail replies. Use only the provided context and never fabricate facts.

Email snippet:
Subject: {email_snippet.get('subject')}
From: {email_snippet.get('from')}
Body preview: {email_snippet.get('snippet')}

Context:
{provenance_block}

Draft a professional reply. Include:
- Greeting
- Key response referencing context ids (e.g., [1])
- Closing with signature placeholder
Provide output as markdown.
"""


def generate_reply(prompt: str) -> str:
    result = generative_model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.4,
            max_output_tokens=512,
            candidate_count=1,
        ),
    )
    return result.text


def basic_safety_check(reply: str) -> None:
    forbidden = ["password", "ssn", "credit card"]
    if any(token in reply.lower() for token in forbidden):
        raise ValueError("Reply contains sensitive terms.")


def create_gmail_draft(creds: credentials.Credentials, email: str, reply: str, thread_id: Optional[str]) -> str:
    gmail = build("gmail", "v1", credentials=creds)
    mime_message = f"From: {email}\r\nTo: {email}\r\nSubject: Re: Automated Draft\r\n\r\n{reply}"

    message = {"raw": mime_message.encode("utf-8").decode("ascii", "ignore")}
    draft_body = {"message": message}
    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    draft = gmail.users().drafts().create(userId=email, body=draft_body).execute()
    if GMAIL_DRAFT_LABEL:
        gmail.users().messages().modify(
            userId=email,
            id=draft["message"]["id"],
            body={"addLabelIds": [GMAIL_DRAFT_LABEL]},
        ).execute()
    return draft["id"]


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/agent/run", response_model=AgentResponse)
async def agent_run(request: AgentRequest) -> AgentResponse:
    if not PROJECT_ID:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Missing PROJECT_ID")

    retrieved = retrieve_context(request.message.get("snippet", ""))
    prompt = build_prompt(request.message, retrieved)
    reply = generate_reply(prompt)
    basic_safety_check(reply)

    creds = build_credentials(request.gmail_user)
    draft_id = create_gmail_draft(creds, request.gmail_user, reply, request.message.get("threadId"))

    return AgentResponse(
        draft_id=draft_id,
        summary="Draft generated and stored in Gmail.",
        retrieved_docs=retrieved,
    )



