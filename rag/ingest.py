#!/usr/bin/env python
"""
Ingest documents into Vertex Matching: chunk, embed, and upsert.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List

from google.cloud import aiplatform
import vertexai
from vertexai.language_models import TextEmbeddingModel

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> Iterable[str]:
    words = text.split()
    step = chunk_size - overlap
    for start in range(0, len(words), step):
        chunk = words[start : start + chunk_size]
        if chunk:
            yield " ".join(chunk)


def embed_chunks(model: TextEmbeddingModel, chunks: List[str]) -> List[List[float]]:
    return [embedding.values for embedding in model.get_embeddings(chunks)]


def upsert_vectors(endpoint_name: str, deployed_index_id: str, embeddings: List[List[float]], chunks: List[str]) -> None:
    endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_name)
    datapoints = []
    for idx, (vector, text) in enumerate(zip(embeddings, chunks)):
        datapoints.append(
            {
                "datapoint_id": f"chunk-{idx}",
                "feature_vector": vector,
                "restriction": [],
                "crowding_tag": "",
                "metadata": json.dumps({"chunk": text}),
            }
        )
    endpoint.upsert_datapoints(datapoints=datapoints, deployed_index_id=deployed_index_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest docs to Vertex Matching")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--index-name", required=True, help="Matching Engine index endpoint resource name")
    parser.add_argument("--deployed-index-id", required=True)
    parser.add_argument("--source", default="docs/kb", help="Folder containing .txt/.md/.pdf files")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)
    args = parser.parse_args()

    vertexai.init(project=args.project, location=args.location)
    aiplatform.init(project=args.project, location=args.location)

    model = TextEmbeddingModel.from_pretrained("text-embedding-004")

    all_chunks: List[str] = []
    for path in Path(args.source).glob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        chunk_list = list(chunk_text(text, args.chunk_size, args.overlap))
        all_chunks.extend(chunk_list)
        print(f"Prepared {len(chunk_list)} chunks from {path.name}")

    embeddings = embed_chunks(model, all_chunks)
    upsert_vectors(args.index_name, args.deployed_index_id, embeddings, all_chunks)
    print(f"Upserted {len(all_chunks)} chunks to {args.index_name}")


if __name__ == "__main__":
    main()


