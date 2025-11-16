# RAG Ingestion

This folder contains the RAG ingestion script for Vertex Matching Engine.

## Setup

### 1. Install Dependencies

This folder has its own `uv` environment. To set it up:

```bash
cd rag
uv sync
```

### 2. Create Index Endpoint and Index

Before ingesting documents, you need to create a Vertex Matching Engine index endpoint and index.

#### Option A: Using the Setup Script (Recommended)

```bash
export PROJECT_ID=loanstax-agentic-ai
export REGION=us-central1

./setup.sh
```

The script will:
- Create an index endpoint (if it doesn't exist)
- Guide you through creating an index
- Show you how to deploy the index to the endpoint

#### Option B: Manual Setup

1. **Create an index endpoint:**
   ```bash
   gcloud ai index-endpoints create \
     --project=$PROJECT_ID \
     --region=$REGION \
     --display-name=gmail-rag-index-endpoint \
     --network=projects/$PROJECT_ID/global/networks/default
   ```

2. **Create an index:**
   ```bash
   # First, create an index metadata file
   # See: https://cloud.google.com/vertex-ai/docs/matching-engine/create-manage-index
   gcloud ai indexes create \
     --project=$PROJECT_ID \
     --region=$REGION \
     --display-name=gmail-rag-index \
     --metadata-file=index_metadata.json
   ```

3. **Deploy the index to the endpoint:**
   ```bash
   gcloud ai index-endpoints deploy-index ENDPOINT_ID \
     --project=$PROJECT_ID \
     --region=$REGION \
     --deployed-index-id=gmail_rag_deployed_index \
     --index=INDEX_ID \
     --display-name=gmail-rag-deployed-index
   ```

For detailed instructions, see the [Vertex AI Matching Engine documentation](https://cloud.google.com/vertex-ai/docs/matching-engine/overview).

## Usage

### List Available Endpoints

First, list available index endpoints:

```bash
uv run ingest.py \
    --project $PROJECT_ID \
    --location us-central1 \
    --list-endpoints
```

### Ingest Documents

Ingest documents from a folder into Vertex Matching Engine:

```bash
uv run ingest.py \
    --project $PROJECT_ID \
    --location us-central1 \
    --index-endpoint your-index-endpoint-id \
    --deployed-index-id your-deployed-index-id \
    --source docs/kb
```

### Arguments

- `--project`: GCP project ID (required)
- `--location`: GCP region (default: us-central1)
- `--index-endpoint`: Index endpoint ID or full resource name (required)
  - Short form: `your-index-endpoint-id` (will be expanded to full resource name)
  - Full form: `projects/PROJECT/locations/LOCATION/indexEndpoints/ENDPOINT_ID`
- `--deployed-index-id`: ID of the deployed index (required)
- `--source`: Folder containing documents to ingest (default: docs/kb)
- `--chunk-size`: Size of text chunks (default: 500)
- `--overlap`: Overlap between chunks (default: 50)

## Example

```bash
export PROJECT_ID=loanstax-agentic-ai

# Using endpoint ID (recommended)
uv run ingest.py \
    --project $PROJECT_ID \
    --location us-central1 \
    --index-endpoint gmail-rag-index-endpoint \
    --deployed-index-id gmail_rag_deployed_index \
    --source docs/kb

# Or using full resource name
uv run ingest.py \
    --project $PROJECT_ID \
    --location us-central1 \
    --index-endpoint projects/72679510753/locations/us-central1/indexEndpoints/7956085929796435968 \
    --deployed-index-id gmail_rag_deployed_index \
    --source docs/kb
```

## Finding Index Endpoint and Deployed Index ID

### Using the script (recommended)

List available index endpoints using the script:

```bash
uv run ingest.py \
    --project $PROJECT_ID \
    --location us-central1 \
    --list-endpoints
```

This will show all available index endpoints and their deployed indexes.

### Using gcloud

Alternatively, to find your index endpoint ID and deployed index ID manually:

1. **List index endpoints:**
   ```bash
   gcloud ai index-endpoints list \
     --project=$PROJECT_ID \
     --region=us-central1
   ```

2. **Get index endpoint details:**
   ```bash
   gcloud ai index-endpoints describe ENDPOINT_ID \
     --project=$PROJECT_ID \
     --region=us-central1
   ```

3. **List deployed indexes:**
   ```bash
   gcloud ai index-endpoints describe ENDPOINT_ID \
     --project=$PROJECT_ID \
     --region=us-central1 \
     --format="value(deployedIndexes)"
   ```

   The output will show deployed indexes with their IDs (e.g., `deployed_index_id_xxx`).

## Requirements

- Python >= 3.11
- `uv` package manager
- GCP credentials configured (`gcloud auth application-default login`)
- Vertex Matching Engine index endpoint created (use `setup.sh` or manual setup)
- Index created and deployed to the endpoint
- Deployed index ID available

## Troubleshooting

### No index endpoints found

If you see "No index endpoints found" when running `--list-endpoints`, you need to create an index endpoint first. Use the `setup.sh` script or follow the manual setup instructions above.

### Invalid argument error

If you get an "Invalid argument" error when trying to ingest:
1. Verify the index endpoint exists: `uv run ingest.py --project $PROJECT_ID --location $REGION --list-endpoints`
2. Verify the deployed index ID is correct
3. Check that the index is actually deployed to the endpoint
4. Verify the embedding dimensions match the index configuration (text-embedding-004 uses 768 dimensions)

