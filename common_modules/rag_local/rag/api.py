
from fastapi import FastAPI
import faiss
import json
import os
import sys
import numpy as np
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedding_models import create_embedding_model

app = FastAPI()

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

@app.get("/rag")
def rag(query: str):
    contexts = search(query)
    context_text = "\n".join([c['text'] for c in contexts])
    answer = f"Based on the documents:\n\n{context_text}\n\nYour question was: {query}"

    return {
        "query": query,
        "contexts": contexts,
        "answer": answer
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
