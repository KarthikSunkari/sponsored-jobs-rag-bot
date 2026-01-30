"""
Embedding service using sentence-transformers for job descriptions.
"""
import os
from typing import List, Optional
from sentence_transformers import SentenceTransformer
import torch
from dotenv import load_dotenv

load_dotenv()


class EmbeddingService:
    """Service for generating embeddings from text."""
    
    def __init__(self, model_name: Optional[str] = None):
        """Initialize embedding model."""
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        print(f"Loading embedding model: {self.model_name}")
        
        # Use CPU for zero-cost operation
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(self.model_name, device=device)
        
        print(f"Model loaded on {device}")
        print(f"Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
    
    def encode(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def encode_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        return [emb.tolist() for emb in embeddings]
    
    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
