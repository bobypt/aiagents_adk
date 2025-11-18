
import os
import sys
import json
import argparse
import faiss
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedding_models import create_embedding_model

def load_files(input_folder):
    docs = []
    for root, _, files in os.walk(input_folder):
        for f in files:
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8") as fp:
                docs.append((f, fp.read()))
    return docs

def chunk_text(text, chunk_size=512, overlap=100):
    """
    Chunk text intelligently respecting sentence and word boundaries.
    
    Args:
        text: The text to chunk
        chunk_size: Target size for each chunk in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        # Calculate the end position
        end = start + chunk_size
        
        # If this is the last chunk, take all remaining text
        if end >= text_length:
            chunks.append(text[start:])
            break
        
        # Try to find a sentence boundary (., !, ?, \n\n)
        # Look within the last 25% of the chunk
        search_start = max(start, end - chunk_size // 4)
        sentence_end = -1
        
        # Check for double newline first (paragraph break)
        para_break = text.rfind('\n\n', search_start, end)
        if para_break != -1:
            sentence_end = para_break + 2
        else:
            # Check for sentence-ending punctuation followed by space or newline
            for punct in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
                pos = text.rfind(punct, search_start, end)
                if pos != -1:
                    sentence_end = pos + len(punct)
                    break
        
        # If no sentence boundary found, try word boundary
        if sentence_end == -1:
            word_end = text.rfind(' ', search_start, end)
            if word_end != -1:
                sentence_end = word_end + 1
        
        # If still no good boundary found, or boundary is too close to start,
        # use the original end position
        if sentence_end == -1 or sentence_end < start + chunk_size // 2:
            sentence_end = end
        
        # Extract chunk
        chunk = text[start:sentence_end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start position forward with overlap
        # Calculate overlap start to maintain context
        if sentence_end < text_length:
            start = max(start + 1, sentence_end - overlap)
        else:
            break
    
    return chunks

def main(input_folder, output_folder, model_type="gemini", model_name="gemini-embedding-001", **kwargs):
    print(f"Loading {model_type} model...")
    model = create_embedding_model(model_type, model_name, **kwargs)
    print(f"Using model: {model.name} (dimension: {model.dimension})")

    print("Loading files...")
    documents = load_files(input_folder)

    chunks = []
    metadata = []

    print("Chunking files...")
    for filename, content in documents:
        chs = chunk_text(content)
        for c in chs:
            chunks.append(c)
            metadata.append({"file": filename, "text": c})

    print(f"Total chunks: {len(chunks)}")

    print("Embedding...")
    embeddings = model.encode(chunks)

    dim = embeddings.shape[1]
    print(f"Embedding shape: {embeddings.shape}")
    
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)

    print("Saving FAISS index...")
    faiss.write_index(index, os.path.join(output_folder, "index.faiss"))

    print("Saving metadata...")
    with open(os.path.join(output_folder, "metadata.json"), "w") as f:
        json.dump(metadata, f)
    
    # Save model info
    model_info = {
        "model_type": model_type,
        "model_name": model.name,
        "dimension": model.dimension,
        "num_chunks": len(chunks)
    }
    with open(os.path.join(output_folder, "model_info.json"), "w") as f:
        json.dump(model_info, f, indent=2)

    print("Done.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build vector embeddings for RAG")
    parser.add_argument("--input", required=True, help="Input folder containing documents")
    parser.add_argument("--output", required=True, help="Output folder for index and metadata")
    parser.add_argument("--model-type", default="gemini", 
                       choices=["sentence-transformers", "gemini"],
                       help="Type of embedding model to use (default: gemini)")
    parser.add_argument("--model-name", default="gemini-embedding-001",
                       help="Specific model name (default: gemini-embedding-001)")
    parser.add_argument("--output-dimension", type=int, default=768,
                       choices=[768, 1536, 3072],
                       help="Output dimension for gemini-embedding-001 (default: 768, options: 768, 1536, 3072)")
    args = parser.parse_args()
    
    kwargs = {}
    if args.model_type == "gemini":
        kwargs["output_dimension"] = args.output_dimension
    
    main(args.input, args.output, args.model_type, args.model_name, **kwargs)
