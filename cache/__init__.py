"""
Cache Module
Redis-based semantic caching with Ollama embeddings
"""

from .redis_client import get_redis_client
from .embeddings import EmbeddingService
from .semantic_cache import SemanticCache

__all__ = [
    "get_redis_client",
    "EmbeddingService",
    "SemanticCache"
]
