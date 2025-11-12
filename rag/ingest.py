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
from google.cloud.aiplatform_v1 import IndexServiceClient
from google.cloud.aiplatform_v1.types import IndexDatapoint
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
    try:
        print(f"Connecting to index endpoint: {endpoint_name}")
        endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_name)
        print(f"Successfully connected to endpoint: {endpoint.resource_name}")
    except Exception as e:
        raise ValueError(
            f"Failed to connect to index endpoint '{endpoint_name}': {e}\n"
            f"Please verify that:\n"
            f"  1. The index endpoint exists in your project\n"
            f"  2. The resource name is correct: {endpoint_name}\n"
            f"  3. You have the necessary permissions\n"
            f"  4. The endpoint is in the correct region\n"
            f"\nTo list available endpoints, run:\n"
            f"  uv run ingest.py --project=<PROJECT_ID> --location=<REGION> --list-endpoints"
        ) from e
    
    # Get the deployed index to find the underlying index ID
    deployed_indexes = getattr(endpoint, 'deployed_indexes', [])
    if not deployed_indexes:
        raise ValueError(
            f"No deployed indexes found on endpoint '{endpoint_name}'.\n"
            f"\nYou need to:\n"
            f"  1. Create an index (with initial embeddings)\n"
            f"  2. Deploy the index to this endpoint\n"
            f"  3. Then you can upsert additional datapoints\n"
            f"\nSee the README.md for instructions on creating and deploying an index.\n"
            f"Or run: ./setup.sh to get started."
        )
    
    # Find the deployed index
    deployed_index = None
    for di in deployed_indexes:
        if di.id == deployed_index_id:
            deployed_index = di
            break
    
    if not deployed_index:
        available_ids = [di.id for di in deployed_indexes]
        raise ValueError(
            f"Deployed index '{deployed_index_id}' not found on endpoint.\n"
            f"Available deployed indexes: {available_ids}\n"
            f"\nTo check deployed indexes, run:\n"
            f"  gcloud ai index-endpoints describe {endpoint_name.split('/')[-1]} --project=<PROJECT_ID> --region=<REGION>"
        )
    
    # Get the index ID from the deployed index
    index_id = deployed_index.index
    print(f"Found deployed index '{deployed_index_id}', underlying index: {index_id}")
    
    # Prepare datapoints using IndexDatapoint
    datapoints = []
    for idx, (vector, text) in enumerate(zip(embeddings, chunks)):
        datapoint = IndexDatapoint(
            datapoint_id=f"chunk-{idx}",
            feature_vector=vector,
        )
        # Add metadata as JSON string if available
        if text:
            # Store metadata in the datapoint (if index schema supports it)
            # Note: Metadata format depends on index configuration
            datapoint.restricts = []  # Empty restricts for now
        datapoints.append(datapoint)
    
    # Use MatchingEngineIndex to upsert datapoints
    try:
        print(f"Upserting {len(datapoints)} datapoints to index: {index_id}")
        index = aiplatform.MatchingEngineIndex(index_name=index_id)
        index.upsert_datapoints(datapoints=datapoints)
        print(f"Successfully upserted {len(datapoints)} datapoints")
    except Exception as e:
        raise ValueError(
            f"Failed to upsert datapoints to index '{index_id}': {e}\n"
            f"Please verify that:\n"
            f"  1. The index exists and is accessible\n"
            f"  2. The embedding dimensions ({len(embeddings[0]) if embeddings else 0}) match the index configuration\n"
            f"  3. You have the necessary permissions to update the index\n"
            f"  4. The index is in the same region as the endpoint"
        ) from e


def list_endpoints(project: str, location: str) -> None:
    """List available index endpoints."""
    print(f"Listing index endpoints in project {project}, location {location}...")
    try:
        aiplatform.init(project=project, location=location)
        endpoints = aiplatform.MatchingEngineIndexEndpoint.list()
        if not endpoints:
            print("No index endpoints found.")
            print("\nTo create an index endpoint, see:")
            print("  https://cloud.google.com/vertex-ai/docs/matching-engine/create-manage-endpoint")
            return
        
        print(f"\nFound {len(endpoints)} index endpoint(s):\n")
        for endpoint in endpoints:
            print(f"  Endpoint ID: {endpoint.resource_name.split('/')[-1]}")
            print(f"  Full name: {endpoint.resource_name}")
            if hasattr(endpoint, 'deployed_indexes') and endpoint.deployed_indexes:
                print(f"  Deployed indexes: {[idx.id for idx in endpoint.deployed_indexes]}")
            print()
    except Exception as e:
        print(f"Error listing endpoints: {e}")
        print("\nTo list endpoints manually, run:")
        print(f"  gcloud ai index-endpoints list --project={project} --region={location}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest docs to Vertex Matching")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument(
        "--index-endpoint",
        help="Matching Engine index endpoint resource name or ID (e.g., projects/PROJECT/locations/LOCATION/indexEndpoints/ENDPOINT_ID or just ENDPOINT_ID)"
    )
    parser.add_argument("--deployed-index-id", help="Deployed index ID")
    parser.add_argument("--source", default="docs/kb", help="Folder containing .txt/.md/.pdf files")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)
    parser.add_argument("--list-endpoints", action="store_true", help="List available index endpoints and exit")
    args = parser.parse_args()
    
    if args.list_endpoints:
        list_endpoints(args.project, args.location)
        return
    
    if not args.index_endpoint:
        parser.error("--index-endpoint is required (or use --list-endpoints to see available endpoints)")
    
    if not args.deployed_index_id:
        parser.error("--deployed-index-id is required")

    vertexai.init(project=args.project, location=args.location)
    aiplatform.init(project=args.project, location=args.location)

    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    
    # Resolve index endpoint resource name
    # Accept either full resource name or just endpoint ID
    if "/" in args.index_endpoint:
        # Full resource name provided
        if "indexEndpoints" not in args.index_endpoint:
            raise ValueError(
                f"Invalid index endpoint format: {args.index_endpoint}. "
                f"Expected format: projects/PROJECT/locations/LOCATION/indexEndpoints/ENDPOINT_ID"
            )
        index_endpoint_name = args.index_endpoint
    else:
        # Just endpoint ID provided, construct full resource name
        index_endpoint_name = f"projects/{args.project}/locations/{args.location}/indexEndpoints/{args.index_endpoint}"

    # Resolve source path - if relative, try relative to repo root first, then current directory
    source_arg = Path(args.source)
    if source_arg.is_absolute():
        source_path = source_arg
    else:
        # Try relative to repo root (parent of rag/ directory)
        script_dir = Path(__file__).parent.parent  # Go up from rag/ingest.py to repo root
        candidate_path = (script_dir / source_arg).resolve()
        if candidate_path.exists() and candidate_path.is_dir():
            source_path = candidate_path
        else:
            # Fall back to relative to current directory
            source_path = Path(args.source).resolve()
    if not source_path.exists():
        raise ValueError(f"Source directory does not exist: {source_path}")
    
    if not source_path.is_dir():
        raise ValueError(f"Source path is not a directory: {source_path}")

    print(f"Scanning for files in: {source_path}")
    all_chunks: List[str] = []
    file_count = 0
    
    # Support recursive file search with common text file extensions
    extensions = {".txt", ".md", ".markdown", ".rst"}
    for path in source_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            print(f"Skipping {path.name} (not a supported text file)")
            continue
        
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                print(f"Warning: {path.name} is empty, skipping")
                continue
                
            chunk_list = list(chunk_text(text, args.chunk_size, args.overlap))
            if not chunk_list:
                print(f"Warning: {path.name} produced no chunks, skipping")
                continue
                
            all_chunks.extend(chunk_list)
            file_count += 1
            print(f"Prepared {len(chunk_list)} chunks from {path.name}")
        except Exception as e:
            print(f"Error processing {path.name}: {e}")
            continue

    if not all_chunks:
        raise ValueError(f"No chunks found in {source_path}. Check that files exist and contain text.")

    print(f"\nTotal: {file_count} files, {len(all_chunks)} chunks")
    print("Generating embeddings...")
    
    # Process embeddings in batches to avoid API limits
    batch_size = 100
    all_embeddings: List[List[float]] = []
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        print(f"Embedding batch {i // batch_size + 1}/{(len(all_chunks) + batch_size - 1) // batch_size}...")
        embeddings = embed_chunks(model, batch)
        all_embeddings.extend(embeddings)
    
    print(f"Upserting {len(all_chunks)} chunks to {index_endpoint_name}...")
    upsert_vectors(index_endpoint_name, args.deployed_index_id, all_embeddings, all_chunks)
    print(f"Successfully upserted {len(all_chunks)} chunks to {index_endpoint_name}")


if __name__ == "__main__":
    main()


