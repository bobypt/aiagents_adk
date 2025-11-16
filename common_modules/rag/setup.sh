#!/usr/bin/env bash
set -euo pipefail

# Script to set up Vertex Matching Engine index endpoint for RAG
# Note: Creating an index requires either pre-computed embeddings or using the Python SDK
# This script creates the endpoint; you'll need to create the index separately

PROJECT_ID=${PROJECT_ID:?Set PROJECT_ID}
REGION=${REGION:-us-central1}
ENDPOINT_ID=${ENDPOINT_ID:-gmail-rag-index-endpoint}

echo "Setting up Vertex Matching Engine index endpoint for RAG..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Endpoint ID: $ENDPOINT_ID"
echo ""

# Check if index endpoint already exists
echo "Checking for existing index endpoints..."
EXISTING_ENDPOINTS=$(gcloud ai index-endpoints list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format="value(name,displayName)" 2>/dev/null || echo "")

# Check if endpoint with matching display name exists
EXISTING_ENDPOINT=""
if [ -n "$EXISTING_ENDPOINTS" ]; then
    while IFS=$'\t' read -r name display_name; do
        if [ "$display_name" = "$ENDPOINT_ID" ]; then
            EXISTING_ENDPOINT="$name"
            break
        fi
    done <<< "$EXISTING_ENDPOINTS"
fi

if [ -n "$EXISTING_ENDPOINT" ]; then
    echo "✓ Index endpoint $ENDPOINT_ID already exists:"
    echo "  $EXISTING_ENDPOINT"
    ENDPOINT_NAME="$EXISTING_ENDPOINT"
else
    echo "Creating index endpoint: $ENDPOINT_ID..."
    echo "This may take a few minutes..."
    ENDPOINT_NAME=$(gcloud ai index-endpoints create \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --display-name="$ENDPOINT_ID" \
        --format="value(name)" 2>&1)
    
    if [ $? -ne 0 ] || [ -z "$ENDPOINT_NAME" ]; then
        echo "Error: Failed to create index endpoint"
        echo "Output: $ENDPOINT_NAME"
        exit 1
    fi
    echo "✓ Created index endpoint: $ENDPOINT_NAME"
fi

# Extract endpoint ID from full resource name
ENDPOINT_RESOURCE_ID=$(echo "$ENDPOINT_NAME" | awk -F'/' '{print $NF}')

echo ""
echo "=========================================="
echo "Index endpoint setup complete!"
echo "=========================================="
echo ""
echo "Endpoint ID: $ENDPOINT_RESOURCE_ID"
echo "Full name: $ENDPOINT_NAME"
echo ""

# Check if index already exists and is deployed
echo "Checking for existing indexes..."
EXISTING_INDEXES=$(gcloud ai indexes list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --filter="displayName:gmail-rag-index" \
    --format="value(name)" 2>/dev/null || echo "")

if [ -n "$EXISTING_INDEXES" ]; then
    echo "✓ Found existing index:"
    INDEX_NAME=$(echo "$EXISTING_INDEXES" | head -1)
    echo "  $INDEX_NAME"
    INDEX_ID=$(echo "$INDEX_NAME" | awk -F'/' '{print $NF}')
    
    # Check if it's deployed
    DEPLOYED=$(gcloud ai index-endpoints describe "$ENDPOINT_RESOURCE_ID" \
        --project="$PROJECT_ID" \
        --region="$REGION" \
        --format="value(deployedIndexes)" 2>/dev/null || echo "")
    
    if [ -z "$DEPLOYED" ] || [ "$DEPLOYED" = "[]" ]; then
        echo ""
        echo "Index exists but is not deployed. Deploying now..."
        echo "This may take 20-30 minutes..."
        gcloud ai index-endpoints deploy-index "$ENDPOINT_RESOURCE_ID" \
            --project="$PROJECT_ID" \
            --region="$REGION" \
            --deployed-index-id=gmail_rag_deployed_index \
            --index="$INDEX_ID" \
            --display-name=gmail-rag-deployed-index \
            --min-replica-count=1 \
            --max-replica-count=1 || {
            echo "Error: Failed to deploy index. You may need to deploy it manually."
            exit 1
        }
        echo "✓ Index deployed successfully!"
    else
        echo "✓ Index is already deployed to the endpoint"
    fi
else
    echo "No existing index found."
    echo ""
    echo "Creating index from documents in docs/kb..."
    echo "This will:"
    echo "  1. Load documents from docs/kb"
    echo "  2. Generate embeddings"
    echo "  3. Create the index"
    echo "  4. Deploy it to the endpoint"
    echo ""
    echo "This may take several minutes..."
    echo ""
    
    # Create index using Python script
    cd "$(dirname "$0")" || exit 1
    uv run python create_index.py \
        --project "$PROJECT_ID" \
        --location "$REGION" \
        --index-name gmail-rag-index \
        --endpoint "$ENDPOINT_RESOURCE_ID" \
        --deployed-index-id gmail_rag_deployed_index \
        --source docs/kb || {
        echo ""
        echo "Error: Failed to create index. Please check the error messages above."
        echo ""
        echo "Manual setup instructions:"
        echo "  1. Create an index using the Vertex AI Console or Python SDK"
        echo "  2. Deploy the index to the endpoint:"
        echo "     gcloud ai index-endpoints deploy-index $ENDPOINT_RESOURCE_ID \\"
        echo "       --project=$PROJECT_ID \\"
        echo "       --region=$REGION \\"
        echo "       --deployed-index-id=gmail_rag_deployed_index \\"
        echo "       --index=<INDEX_ID> \\"
        echo "       --display-name=gmail-rag-deployed-index"
        exit 1
    }
    echo ""
    echo "✓ Index created and deployed successfully!"
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "You can now ingest documents using:"
echo "  cd rag"
echo "  uv run ingest.py \\"
echo "    --project $PROJECT_ID \\"
echo "    --location $REGION \\"
echo "    --index-endpoint $ENDPOINT_RESOURCE_ID \\"
    echo "    --deployed-index-id=gmail_rag_deployed_index \\"
echo "    --source docs/kb"
echo ""

