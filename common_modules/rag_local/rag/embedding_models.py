"""
Embedding model abstraction layer supporting multiple embedding providers.
"""

import os
import numpy as np
from typing import List, Optional
from sentence_transformers import SentenceTransformer
import google.generativeai as genai


class EmbeddingModel:
    """Base class for embedding models."""
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts into embeddings."""
        raise NotImplementedError
    
    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        raise NotImplementedError
    
    @property
    def name(self) -> str:
        """Return the model name."""
        raise NotImplementedError


class SentenceTransformerModel(EmbeddingModel):
    """Wrapper for SentenceTransformer models."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        # Get dimension by encoding a dummy text
        self._dimension = self._model.get_sentence_embedding_dimension()
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts using SentenceTransformer."""
        return self._model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def name(self) -> str:
        return f"sentence-transformers/{self.model_name}"


class GeminiEmbeddingModel(EmbeddingModel):
    """Wrapper for Google Gemini embedding models."""
    
    def __init__(self, model_name: str = "gemini-embedding-001", api_key: Optional[str] = None, output_dimension: int = 768):
        self.model_name = model_name
        self.output_dimension = output_dimension
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable must be set for Gemini models")
        
        genai.configure(api_key=api_key)
        
        # Dimension mapping for Gemini models
        # gemini-embedding-001 supports flexible output_dimension (768, 1536, or 3072)
        self._dimension_map = {
            "text-embedding-004": 768,
            "gemini-embedding-001": output_dimension,  # Flexible: 768, 1536, or 3072
            "textembedding-gecko@001": 768,
            "textembedding-gecko@002": 768,
            "textembedding-gecko@003": 768,
            "textembedding-gecko-multilingual@001": 768,
            "models/embedding-001": output_dimension,  # Also supports flexible dimensions
        }
        self._dimension = self._dimension_map.get(model_name, output_dimension)
    
    def encode(self, texts: List[str], batch_size: int = 100) -> np.ndarray:
        """Encode texts using Gemini API."""
        embeddings = []
        
        # Process in batches to avoid rate limits
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = []
            
            for text in batch:
                try:
                    # Format model name properly for Gemini API
                    model_path = self.model_name
                    if not model_path.startswith("models/"):
                        model_path = f"models/{model_path}"
                    
                    # Build embed_content parameters
                    embed_params = {
                        "model": model_path,
                        "content": text,
                        "task_type": "retrieval_document"
                    }
                    
                    # Add output_dimension for models that support it (gemini-embedding-001, models/embedding-001)
                    if self.model_name in ["gemini-embedding-001", "models/embedding-001"]:
                        embed_params["output_dimensionality"] = self.output_dimension
                    
                    result = genai.embed_content(**embed_params)
                    batch_embeddings.append(result['embedding'])
                except Exception as e:
                    print(f"Error embedding text: {e}")
                    # Use zero vector as fallback
                    batch_embeddings.append([0.0] * self._dimension)
            
            embeddings.extend(batch_embeddings)
        
        return np.array(embeddings)
    
    def encode_query(self, query: str) -> np.ndarray:
        """Encode a query (different task type for queries)."""
        try:
            # Format model name properly for Gemini API
            model_path = self.model_name
            if not model_path.startswith("models/"):
                model_path = f"models/{model_path}"
            
            # Build embed_content parameters
            embed_params = {
                "model": model_path,
                "content": query,
                "task_type": "retrieval_query"
            }
            
            # Add output_dimension for models that support it
            if self.model_name in ["gemini-embedding-001", "models/embedding-001"]:
                embed_params["output_dimensionality"] = self.output_dimension
            
            result = genai.embed_content(**embed_params)
            return np.array([result['embedding']])
        except Exception as e:
            print(f"Error embedding query: {e}")
            return np.array([[0.0] * self._dimension])
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def name(self) -> str:
        return f"gemini/{self.model_name}"


def create_embedding_model(model_type: str, model_name: Optional[str] = None, **kwargs) -> EmbeddingModel:
    """
    Factory function to create embedding models.
    
    Args:
        model_type: Type of model - "sentence-transformers" or "gemini"
        model_name: Specific model name (optional, uses defaults if not provided)
        **kwargs: Additional arguments passed to model constructors (e.g., output_dimension for Gemini)
    
    Returns:
        EmbeddingModel instance
    """
    if model_type == "sentence-transformers" or model_type == "st":
        return SentenceTransformerModel(model_name or "all-MiniLM-L6-v2")
    elif model_type == "gemini":
        return GeminiEmbeddingModel(model_name or "gemini-embedding-001", **kwargs)
    else:
        raise ValueError(f"Unknown model type: {model_type}. Use 'sentence-transformers' or 'gemini'")

