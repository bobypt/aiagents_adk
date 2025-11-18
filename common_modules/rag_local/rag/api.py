
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import faiss
import json
import os
import sys
import numpy as np
import uvicorn
import firebase_admin
from firebase_admin import auth

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedding_models import create_embedding_model

app = FastAPI()
security = HTTPBearer()

# Initialize Firebase Admin SDK for token validation
# Only needs project ID - no service account required
firebase_initialized = False
try:
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    if project_id:
        # Initialize with just project ID - SDK will fetch public keys automatically
        firebase_admin.initialize_app(options={"projectId": project_id})
        firebase_initialized = True
        print(f"Firebase Admin initialized with project ID: {project_id}", flush=True)
    else:
        # Try to initialize without explicit project ID (may work in some environments)
        try:
            firebase_admin.initialize_app()
            firebase_initialized = True
            print("Firebase Admin initialized (project ID auto-detected)", flush=True)
        except Exception as e:
            print(f"Warning: Firebase Admin initialization failed. Set FIREBASE_PROJECT_ID env var. Error: {e}", flush=True)
except Exception as e:
    print(f"Warning: Firebase Admin initialization failed: {e}. Auth validation will be disabled.", flush=True)

# Load model info to determine which model was used
model_info_path = "output/model_info.json"
model_kwargs = {}
if os.path.exists(model_info_path):
    with open(model_info_path, "r") as f:
        model_info = json.load(f)
    model_type = model_info.get("model_type", "gemini")
    model_name = model_info.get("model_name", None)
    if model_name:
        # Extract model name from full name (e.g., "gemini/gemini-embedding-001")
        if "/" in model_name:
            model_name = model_name.split("/", 1)[1]
    # Get output_dimension if it was saved
    if model_info.get("dimension"):
        model_kwargs["output_dimension"] = model_info.get("dimension")
else:
    # Default to gemini-embedding-001
    model_type = "gemini"
    model_name = "gemini-embedding-001"
    model_kwargs["output_dimension"] = 768

model = create_embedding_model(model_type, model_name, **model_kwargs)
index = faiss.read_index("output/index.faiss")

with open("output/metadata.json") as f:
    metadata = json.load(f)

def search(query, k=3):
    if hasattr(model, 'encode_query'):
        # Gemini model with special query encoding
        q_emb = model.encode_query(query)
    else:
        q_emb = model.encode([query])
    distances, indices = index.search(q_emb, k)
    results = [metadata[i] for i in indices[0]]
    return results


async def verify_firebase_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Verify Firebase ID token and return decoded token claims.
    """
    if not firebase_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase Admin SDK not initialized. Set FIREBASE_PROJECT_ID environment variable."
        )
    
    token = credentials.credentials
    try:
        # Verify the ID token
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


class RAGRequest(BaseModel):
    query: str


@app.post("/rag")
async def rag(request: RAGRequest, user: dict = Depends(verify_firebase_token)):
    """
    Perform RAG search with Firebase authentication.
    Requires Authorization header with Bearer token (Firebase ID token).
    """
    query = request.query
    contexts = search(query)
    context_text = "\n".join([c['text'] for c in contexts])
    answer = f"Based on the documents:\n\n{context_text}\n\nYour question was: {query}"

    return {
        "query": query,
        "contexts": contexts,
        "answer": answer,
        "user_id": user.get("uid"),
        "user_email": user.get("email")
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
