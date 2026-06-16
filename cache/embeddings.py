"""
Embedding Service using Ollama
Uses local mxbai-embed-large model for semantic similarity
"""

import ollama
from typing import List
from loguru import logger
from config import Config


class EmbeddingService:
    """
    Ollama-based embedding service for semantic caching
    
    Features:
    - Local embedding model (completely free)
    - mxbai-embed-large (1024 dimensions)
    - Fast inference (~50ms per query)
    
    Usage:
        embedder = EmbeddingService()
        embedding = embedder.embed_query("Find cheap flights to Miami")
        # Returns: [0.123, -0.456, ...] (1024 dimensions)
    """
    
    def __init__(self):
        """
        Initialize Ollama Embedding Service
        
        Raises:
            RuntimeError: If Ollama is not available or model not installed
        """
        self.model = Config.OLLAMA_EMBEDDING_MODEL
        self.ollama_host = Config.OLLAMA_HOST
        self.embedding_dim = Config.OLLAMA_EMBEDDING_DIM
        
        # Verify Ollama and model availability
        self._verify_setup()
        
        logger.info(
            f"Embedding Service initialized: {self.model} "
            f"({self.embedding_dim} dimensions)"
        )
    
    def _verify_setup(self):
        """
        Verify Ollama is running and model is installed
        """
        try:
            # List available models
            models = ollama.list()
            model_names = [m['name'] for m in models.get('models', [])]
            
            # Check if our model is available
            if self.model not in model_names:
                logger.error(
                    f"Ollama model '{self.model}' not found. "
                    f"Available models: {model_names}"
                )
                logger.error(f"Please run: ollama pull {self.model}")
                raise RuntimeError(
                    f"Ollama model '{self.model}' not installed. "
                    f"Run: ollama pull {self.model}"
                )
            
            logger.debug(f"Ollama model '{self.model}' verified")
            
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            logger.error(
                "Make sure Ollama is running. "
                "Visit: https://ollama.com/download"
            )
            raise RuntimeError(f"Ollama not available: {e}")
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a query string
        
        Args:
            query: Text to embed
        
        Returns:
            List[float]: Embedding vector (1024 dimensions)
        
        Raises:
            RuntimeError: If embedding generation fails
        
        Example:
            >>> embedder = EmbeddingService()
            >>> embedding = embedder.embed_query("cheap flights to Miami")
            >>> len(embedding)
            1024
            >>> type(embedding[0])
            <class 'float'>
        """
        try:
            response = ollama.embeddings(
                model=self.model,
                prompt=query
            )
            
            embedding = response['embedding']
            
            # Validate embedding
            if len(embedding) != self.embedding_dim:
                logger.warning(
                    f"Unexpected embedding dimension: {len(embedding)} "
                    f"(expected {self.embedding_dim})"
                )
            
            logger.debug(f"Generated embedding for: '{query[:50]}...' ({len(embedding)} dims)")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
    
    def embed_batch(self, queries: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple queries
        
        Args:
            queries: List of text strings
        
        Returns:
            List[List[float]]: List of embedding vectors
        
        Example:
            >>> embedder = EmbeddingService()
            >>> queries = ["flight to Miami", "hotel in NYC"]
            >>> embeddings = embedder.embed_batch(queries)
            >>> len(embeddings)
            2
            >>> len(embeddings[0])
            1024
        """
        embeddings = []
        
        for query in queries:
            embedding = self.embed_query(query)
            embeddings.append(embedding)
        
        logger.debug(f"Generated {len(embeddings)} embeddings")
        
        return embeddings
    
    def calculate_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
        
        Returns:
            float: Cosine similarity (0.0 to 1.0)
        
        Example:
            >>> embedder = EmbeddingService()
            >>> emb1 = embedder.embed_query("cheap flights to Miami")
            >>> emb2 = embedder.embed_query("affordable Miami flights")
            >>> similarity = embedder.calculate_similarity(emb1, emb2)
            >>> similarity > 0.85  # Should be very similar
            True
        """
        import numpy as np
        
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        # Calculate cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # Ensure result is between 0 and 1
        return max(0.0, min(1.0, float(similarity)))
    
    @property
    def model_info(self) -> dict:
        """
        Get model information
        
        Returns:
            dict: Model metadata
        """
        return {
            "model": self.model,
            "embedding_dim": self.embedding_dim,
            "ollama_host": self.ollama_host
        }


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    print("Testing Ollama Embedding Service...\n")
    
    try:
        # Initialize service
        embedder = EmbeddingService()
        print(f"✅ Service initialized: {embedder.model_info}\n")
        
        # Test single embedding
        query1 = "Find cheap flights from SFO to Miami"
        embedding1 = embedder.embed_query(query1)
        print(f"Query 1: {query1}")
        print(f"Embedding dimensions: {len(embedding1)}")
        print(f"First 5 values: {embedding1[:5]}\n")
        
        # Test similar query
        query2 = "cheap flight SFO to Miami"
        embedding2 = embedder.embed_query(query2)
        
        similarity = embedder.calculate_similarity(embedding1, embedding2)
        print(f"Query 2: {query2}")
        print(f"Similarity: {similarity:.3f}")
        print(f"✅ Similar queries detected (threshold: 0.85)\n" if similarity > 0.85 else "")
        
        # Test different query
        query3 = "hotel in New York with pool"
        embedding3 = embedder.embed_query(query3)
        
        similarity2 = embedder.calculate_similarity(embedding1, embedding3)
        print(f"Query 3: {query3}")
        print(f"Similarity to Query 1: {similarity2:.3f}")
        print(f"Different queries detected\n" if similarity2 < 0.85 else "")
        
        # Test batch
        queries = [
            "weekend trip to Miami",
            "business hotel in NYC",
            "beach vacation Florida"
        ]
        embeddings = embedder.embed_batch(queries)
        print(f"✅ Batch embedding: {len(embeddings)} queries processed")
        
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure Ollama is running: ollama serve")
        print("2. Install the model: ollama pull mxbai-embed-large")
        print("3. Verify: ollama list")
