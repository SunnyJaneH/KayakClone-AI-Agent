"""
Semantic Cache using Redis
Caches LLM responses with semantic similarity matching
If a similar query (cosine similarity > 0.85) exists, returns cached response
"""

import json
import numpy as np
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from .redis_client import get_redis_client
from .embeddings import EmbeddingService
from config import Config


class SemanticCache:
    """
    Semantic cache for LLM responses
    
    Features:
    - Similarity-based retrieval (threshold: 0.85)
    - Automatic expiration (7 days default)
    - Uses Ollama embeddings (free, local)
    - Stores in Redis for fast access
    
    How it works:
    1. User query → Generate embedding
    2. Search for similar embeddings in cache
    3. If similarity > 0.85 → Return cached response
    4. Else → Call LLM → Store new embedding + response
    
    Usage:
        cache = SemanticCache(redis_client, embedding_service)
        
        # Try to get from cache
        result = cache.get("cheap flights to Miami")
        if result:
            return result['response']
        
        # Cache miss - call LLM
        response = llm.generate(query)
        cache.set(query, response)
    """
    
    def __init__(
        self,
        redis_client,
        embedding_service: EmbeddingService,
        threshold: float = 0.85,
        ttl_days: int = 7
    ):
        """
        Initialize Semantic Cache
        
        Args:
            redis_client: Redis client instance
            embedding_service: Ollama embedding service
            threshold: Similarity threshold (default: 0.85)
            ttl_days: Cache expiration in days (default: 7)
        """
        self.redis = redis_client
        self.embeddings = embedding_service
        self.threshold = threshold
        self.ttl_seconds = ttl_days * 24 * 3600
        
        self.cache_key_prefix = "cache:"
        self.index_key = "cache:index"  # List of all cache keys
        
        logger.info(
            f"Semantic Cache initialized: "
            f"threshold={threshold}, ttl={ttl_days} days"
        )
    
    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Try to get cached response for similar query
        
        Args:
            query: User query string
        
        Returns:
            dict or None: 
                {
                    "cached_query": original cached query,
                    "response": cached response,
                    "similarity": similarity score
                }
                Returns None if no similar query found
        
        Example:
            >>> cache = SemanticCache(redis, embedder)
            >>> result = cache.get("cheap flights to Miami")
            >>> if result:
            ...     print(f"Cache hit! Similarity: {result['similarity']}")
            ...     return result['response']
        """
        try:
            # Generate embedding for query
            query_embedding = self.embeddings.embed_query(query)
            
            # Get all cache keys
            cache_keys = self.redis.smembers(self.index_key)
            
            if not cache_keys:
                logger.debug("Cache empty")
                return None
            
            # Search for most similar cached query
            best_similarity = 0.0
            best_match = None
            
            for cache_key in cache_keys:
                # Get cached data
                cached_data = self.redis.hgetall(cache_key)
                
                if not cached_data:
                    # Key expired or deleted
                    self.redis.srem(self.index_key, cache_key)
                    continue
                
                # Get cached embedding
                cached_embedding_bytes = cached_data.get(b"embedding")
                if not cached_embedding_bytes:
                    continue
                
                # Convert bytes to numpy array
                cached_embedding = np.frombuffer(
                    cached_embedding_bytes,
                    dtype=np.float32
                ).tolist()
                
                # Calculate similarity
                similarity = self.embeddings.calculate_similarity(
                    query_embedding,
                    cached_embedding
                )
                
                # Track best match
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = {
                        "cache_key": cache_key,
                        "cached_query": cached_data.get(b"query", b"").decode('utf-8'),
                        "response": json.loads(cached_data.get(b"response", b"{}")),
                        "similarity": similarity
                    }
            
            # Check if best match exceeds threshold
            if best_match and best_similarity >= self.threshold:
                logger.info(
                    f"[Cache Hit] Query: '{query}' | "
                    f"Matched: '{best_match['cached_query']}' | "
                    f"Similarity: {best_similarity:.3f}"
                )
                return best_match
            else:
                logger.debug(
                    f"[Cache Miss] Query: '{query}' | "
                    f"Best similarity: {best_similarity:.3f} < {self.threshold}"
                )
                return None
                
        except Exception as e:
            logger.error(f"Error getting from cache: {e}")
            return None
    
    def set(self, query: str, response: Any):
        """
        Store query and response in cache
        
        Args:
            query: User query string
            response: LLM response (will be JSON serialized)
        
        Example:
            >>> cache.set("cheap flights to Miami", {"origin": "flexible", "destination": "Miami"})
        """
        try:
            # Generate embedding
            query_embedding = self.embeddings.embed_query(query)
            
            # Generate unique cache key
            cache_key = self._generate_cache_key(query)
            
            # Convert embedding to bytes
            embedding_bytes = np.array(query_embedding, dtype=np.float32).tobytes()
            
            # Store in Redis hash
            self.redis.hset(
                cache_key,
                mapping={
                    "query": query,
                    "response": json.dumps(response),
                    "embedding": embedding_bytes,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Set expiration
            self.redis.expire(cache_key, self.ttl_seconds)
            
            # Add to index
            self.redis.sadd(self.index_key, cache_key)
            
            logger.debug(f"Cached query: '{query}' with key: {cache_key}")
            
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
    
    def _generate_cache_key(self, query: str) -> str:
        """
        Generate unique cache key from query
        
        Args:
            query: Query string
        
        Returns:
            str: Cache key (e.g., "cache:a1b2c3d4")
        """
        # Use hash of query for unique key
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]
        return f"{self.cache_key_prefix}{query_hash}"
    
    def clear(self):
        """Clear all cache entries"""
        try:
            cache_keys = self.redis.smembers(self.index_key)
            
            if cache_keys:
                # Delete all cache keys
                self.redis.delete(*cache_keys)
                # Clear index
                self.redis.delete(self.index_key)
                logger.info(f"Cleared {len(cache_keys)} cache entries")
            else:
                logger.info("Cache already empty")
                
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            dict: Cache statistics
        """
        try:
            cache_keys = self.redis.smembers(self.index_key)
            total_entries = len(cache_keys)
            
            # Sample a few entries for stats
            sample_queries = []
            for key in list(cache_keys)[:5]:
                cached_data = self.redis.hgetall(key)
                if cached_data:
                    sample_queries.append(
                        cached_data.get(b"query", b"").decode('utf-8')
                    )
            
            return {
                "total_entries": total_entries,
                "threshold": self.threshold,
                "ttl_days": self.ttl_seconds / (24 * 3600),
                "sample_queries": sample_queries
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    from .redis_client import get_redis_client
    from .embeddings import EmbeddingService
    
    print("Testing Semantic Cache...\n")
    
    try:
        # Initialize
        redis_client = get_redis_client()
        embedding_service = EmbeddingService()
        cache = SemanticCache(redis_client, embedding_service, threshold=0.85)
        
        print("✅ Semantic Cache initialized\n")
        
        # Clear previous cache
        cache.clear()
        
        # Test 1: Cache miss
        print("=== Test 1: Cache Miss ===")
        query1 = "Find cheap flights from SFO to Miami"
        result = cache.get(query1)
        print(f"Query: {query1}")
        print(f"Result: {result}")
        print(f"✅ Cache miss (expected)\n")
        
        # Store in cache
        response1 = {
            "origin": "SFO",
            "destination": "Miami",
            "budget": None,
            "constraints": []
        }
        cache.set(query1, response1)
        print(f"✅ Stored in cache\n")
        
        # Test 2: Cache hit with similar query
        print("=== Test 2: Cache Hit (Similar Query) ===")
        query2 = "cheap flight SFO to Miami"  # Very similar
        result = cache.get(query2)
        print(f"Query: {query2}")
        if result:
            print(f"✅ Cache hit!")
            print(f"   Original query: {result['cached_query']}")
            print(f"   Similarity: {result['similarity']:.3f}")
            print(f"   Response: {result['response']}\n")
        else:
            print("❌ Cache miss (unexpected)\n")
        
        # Test 3: Cache miss with different query
        print("=== Test 3: Cache Miss (Different Query) ===")
        query3 = "hotel in New York with pool"
        result = cache.get(query3)
        print(f"Query: {query3}")
        print(f"Result: {result}")
        print(f"✅ Cache miss (expected - different topic)\n")
        
        # Get stats
        stats = cache.get_stats()
        print("=== Cache Statistics ===")
        print(json.dumps(stats, indent=2))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure:")
        print("1. Redis is running: redis-server")
        print("2. Ollama is running: ollama serve")
        print("3. Model is installed: ollama pull mxbai-embed-large")
