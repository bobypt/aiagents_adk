#!/usr/bin/env python
"""
Create a Vertex Matching Engine index from documents and deploy it to an endpoint.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import List

from google.cloud import aiplatform
from google.cloud.aiplatform.matching_engine import MatchingEngineIndex
from google.cloud.aiplatform.matching_engine.matching_engine_index_config import (
    DistanceMeasureType,
)
from google.cloud.aiplatform_v1.types import IndexDatapoint
import vertexai
from vertexai.language_models import TextEmbeddingModel

PROJECT_ID = os.environ.get("PROJECT_ID")
LOCATION = os.environ.get("LOCATION", "us-central1")
EMBEDDING_DIMENSION = 768  # text-embedding-004 dimension


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into chunks."""
    words = text.split()
    step = chunk_size - overlap
    chunks = []
    for start in range(0, len(words), step):
        chunk = words[start : start + chunk_size]
        if chunk:
            chunks.append(" ".join(chunk))
    return chunks


def create_index_from_documents(
    project_id: str,
    location: str,
    index_display_name: str,
    endpoint_name: str,
    deployed_index_id: str,
    source_dir: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> str:
    """Create an index from documents and deploy it to an endpoint."""
    print(f"Initializing Vertex AI...")
    vertexai.init(project=project_id, location=location)
    aiplatform.init(project=project_id, location=location)

    print(f"Loading embedding model...")
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")

    # Load and chunk documents
    source_path = Path(source_dir).resolve()
    if not source_path.exists() or not source_path.is_dir():
        raise ValueError(f"Source directory does not exist: {source_path}")

    print(f"Scanning for files in: {source_path}")
    all_chunks = []
    extensions = {".txt", ".md", ".markdown", ".rst"}
    
    for path in source_path.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        
        try:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                continue
            
            chunk_list = chunk_text(text, chunk_size, overlap)
            all_chunks.extend(chunk_list)
            print(f"Prepared {len(chunk_list)} chunks from {path.name}")
        except Exception as e:
            print(f"Error processing {path.name}: {e}")
            continue

    if not all_chunks:
        raise ValueError(f"No chunks found in {source_path}")

    print(f"\nTotal: {len(all_chunks)} chunks")
    print(f"Generating embeddings...")

    # Generate embeddings in batches
    batch_size = 100
    all_embeddings = []
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        print(f"Embedding batch {i // batch_size + 1}/{(len(all_chunks) + batch_size - 1) // batch_size}...")
        embeddings = [embedding.values for embedding in model.get_embeddings(batch)]
        all_embeddings.extend(embeddings)

    print(f"Creating index: {index_display_name}")
    
    # Create index with Tree-AH algorithm (good for most use cases)
    # Note: Vertex Matching Engine requires initial embeddings to create an index
    # We'll create the index with initial embeddings, then deploy it
    print("Creating index (this may take a few minutes)...")
    print("Note: Vertex Matching Engine may require initial embeddings uploaded to Cloud Storage.")
    print("Attempting to create index with STREAM_UPDATE method...")
    
    # Note: According to Vertex AI docs, creating an index with STREAM_UPDATE might
    # still require initial data. If this fails, we'll need to upload embeddings to GCS first.
    # The distance_measure_type parameter might have serialization issues with the enum.
    # Try omitting it first to use the default, or use the enum directly if needed.
    try:
        # Try brute force index first (simpler, supports stream updates)
        # Note: distance_measure_type is optional - if omitted, it might use a default
        print("Attempting to create brute force index...")
        # Try without distance_measure_type first (use default)
        index = MatchingEngineIndex.create_brute_force_index(
            display_name=index_display_name,
            contents_delta_uri=None,
            dimensions=EMBEDDING_DIMENSION,
            # distance_measure_type is optional - try omitting it
            index_update_method="STREAM_UPDATE",
            project=project_id,
            location=location,
        )
        print("Brute force index created successfully!")
    except Exception as e1:
        print(f"Brute force index creation failed (without distance_measure_type): {e1}")
        print("Trying with distance_measure_type as enum...")
        try:
            # Try with enum directly
            index = MatchingEngineIndex.create_brute_force_index(
                display_name=index_display_name,
                contents_delta_uri=None,
                dimensions=EMBEDDING_DIMENSION,
                distance_measure_type=DistanceMeasureType.DOT_PRODUCT_DISTANCE,
                index_update_method="STREAM_UPDATE",
                project=project_id,
                location=location,
            )
            print("Brute force index created successfully with enum!")
        except Exception as e2:
            print(f"Brute force index creation failed (with enum): {e2}")
            print("This likely means we need to upload embeddings to Cloud Storage first.")
            print("\nPlease create the index manually using one of these methods:")
            print("1. Use Vertex AI Console: https://console.cloud.google.com/vertex-ai/matching-engine/indexes")
            print("2. Upload embeddings to Cloud Storage and create index from there")
            print("3. Use gcloud CLI to create index from Cloud Storage")
            raise ValueError(
                f"Failed to create index with both methods:\n"
                f"Without distance_measure_type: {e1}\n"
                f"With enum: {e2}\n"
                f"\nVertex Matching Engine may require initial embeddings uploaded to Cloud Storage.\n"
                f"You can either:\n"
                f"  1. Upload embeddings to Cloud Storage and create index from there\n"
                f"  2. Use the Vertex AI Console to create the index\n"
                f"  3. Use gcloud CLI: gcloud ai indexes create --metadata-file=index_metadata.json\n"
                f"\nSee the README.md for more details."
            ) from e2
    
    print(f"Index created: {index.resource_name}")
    print(f"Waiting for index to be ready...")
    index.wait()
    print(f"Index is ready!")

    # Add initial datapoints
    print(f"Adding {len(all_chunks)} initial datapoints to index...")
    datapoints = []
    for idx, (vector, chunk) in enumerate(zip(all_embeddings, all_chunks)):
        datapoint = IndexDatapoint(
            datapoint_id=f"chunk-{idx}",
            feature_vector=vector,
        )
        # Store chunk text in metadata (if index supports it)
        # Note: Metadata format depends on index schema
        datapoints.append(datapoint)
    
    # Upsert in batches
    batch_size = 100
    for i in range(0, len(datapoints), batch_size):
        batch = datapoints[i:i + batch_size]
        print(f"Upserting batch {i // batch_size + 1}/{(len(datapoints) + batch_size - 1) // batch_size}...")
        index.upsert_datapoints(datapoints=batch)
    
    print(f"Added {len(all_chunks)} datapoints to index")

    # Deploy index to endpoint
    print(f"Deploying index to endpoint: {endpoint_name}")
    print("Note: This may take 20-30 minutes...")
    endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_name)
    
    # Validate and normalize deployed_index_id format: must start with a letter and contain only letters, numbers, and underscores
    original_deployed_index_id = deployed_index_id
    # Replace hyphens with underscores
    deployed_index_id = deployed_index_id.replace("-", "_")
    # Remove any other invalid characters (keep only letters, numbers, underscores)
    deployed_index_id = re.sub(r"[^a-zA-Z0-9_]", "_", deployed_index_id)
    # Ensure it starts with a letter
    if not deployed_index_id[0].isalpha():
        # If it doesn't start with a letter, prefix with 'idx_'
        deployed_index_id = f"idx_{deployed_index_id}"
    
    print(f"Using deployed index ID: {deployed_index_id}")
    
    endpoint.deploy_index(
        index=index,
        deployed_index_id=deployed_index_id,
        display_name=deployed_index_id.replace("_", "-"),  # Display name can have hyphens
        min_replica_count=1,
        max_replica_count=1,
    )
    
    print(f"Deployment initiated successfully!")
    print(f"Index resource name: {index.resource_name}")
    print(f"Index ID: {index.resource_name.split('/')[-1]}")
    print(f"Deployed index ID: {deployed_index_id}")
    print(f"Endpoint: {endpoint_name}")
    print("")
    print("Note: Deployment is asynchronous and may take 20-30 minutes.")
    print("You can check deployment status with:")
    print(f"  gcloud ai index-endpoints describe {endpoint_name.split('/')[-1]} \\")
    print(f"    --project={project_id} \\")
    print(f"    --region={location}")
    print("")
    print("Once deployed, you can use the index for queries and ingest more documents.")
    
    return index.resource_name


def main():
    parser = argparse.ArgumentParser(description="Create and deploy a Matching Engine index")
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="us-central1")
    parser.add_argument("--index-name", default="gmail-rag-index")
    parser.add_argument("--endpoint", required=True, help="Index endpoint resource name or ID")
    parser.add_argument("--deployed-index-id", default="gmail_rag_deployed_index")
    parser.add_argument("--source", default="docs/kb")
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)
    args = parser.parse_args()

    # Resolve endpoint name
    if "/" in args.endpoint:
        endpoint_name = args.endpoint
    else:
        endpoint_name = f"projects/{args.project}/locations/{args.location}/indexEndpoints/{args.endpoint}"

    # Resolve source path
    source_arg = Path(args.source)
    if source_arg.is_absolute():
        source_path = str(source_arg)
    else:
        script_dir = Path(__file__).parent.parent
        candidate_path = script_dir / source_arg
        if candidate_path.exists():
            source_path = str(candidate_path.resolve())
        else:
            source_path = str(Path(args.source).resolve())

    create_index_from_documents(
        project_id=args.project,
        location=args.location,
        index_display_name=args.index_name,
        endpoint_name=endpoint_name,
        deployed_index_id=args.deployed_index_id,
        source_dir=source_path,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )


if __name__ == "__main__":
    main()

