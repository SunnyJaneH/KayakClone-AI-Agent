"""
Redis Client Management
Handles Redis connections for semantic caching
"""

import redis
from functools import lru_cache
from loguru import logger
from config import Config


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    """
    Get Redis client singleton
    
    Returns:
        redis.Redis: Connected Redis client
    
    Raises:
        redis.ConnectionError: If cannot connect to Redis
    """
    try:
        client = redis.Redis(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            password=Config.REDIS_PASSWORD if Config.REDIS_PASSWORD else None,
            db=Config.REDIS_DB,
            decode_responses=False,  # Keep as bytes for vector operations
            socket_timeout=5,
            socket_connect_timeout=5
        )
        
        # Test connection
        client.ping()
        
        logger.info(
            f"Redis connected: {Config.REDIS_HOST}:{Config.REDIS_PORT} "
            f"(DB: {Config.REDIS_DB})"
        )
        
        return client
        
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        logger.warning(
            "Redis is not available. Semantic caching will be disabled. "
            "Make sure Redis is running: redis-server"
        )
        raise


def check_redis_health() -> bool:
    """
    Check if Redis is healthy
    
    Returns:
        bool: True if Redis is accessible
    """
    try:
        client = get_redis_client()
        client.ping()
        return True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        return False


def clear_cache_by_pattern(pattern: str = "cache:*"):
    """
    Clear cache entries matching pattern
    
    Args:
        pattern: Redis key pattern (default: "cache:*")
    
    Example:
        >>> clear_cache_by_pattern("cache:*")  # Clear all cache
        >>> clear_cache_by_pattern("cache:123*")  # Clear specific prefix
    """
    try:
        client = get_redis_client()
        keys = client.keys(pattern)
        
        if keys:
            deleted = client.delete(*keys)
            logger.info(f"Deleted {deleted} cache entries matching '{pattern}'")
        else:
            logger.info(f"No cache entries found matching '{pattern}'")
            
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")


def get_cache_stats() -> dict:
    """
    Get Redis cache statistics
    
    Returns:
        dict: Cache statistics
    """
    try:
        client = get_redis_client()
        info = client.info()
        
        # Get cache key count
        cache_keys = len(client.keys("cache:*"))
        
        return {
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "used_memory": info.get("used_memory_human"),
            "total_keys": info.get("db0", {}).get("keys", 0),
            "cache_keys": cache_keys,
            "uptime_days": info.get("uptime_in_days")
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {}


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    # Test Redis connection
    print("Testing Redis connection...")
    
    try:
        client = get_redis_client()
        print(f"✅ Redis connected successfully")
        
        # Test basic operations
        client.set("test_key", "test_value")
        value = client.get("test_key")
        print(f"✅ Test write/read: {value.decode() if value else 'None'}")
        
        # Clean up
        client.delete("test_key")
        
        # Get stats
        stats = get_cache_stats()
        print(f"\nRedis Stats:")
        for key, val in stats.items():
            print(f"  {key}: {val}")
        
        # Check health
        is_healthy = check_redis_health()
        print(f"\n✅ Redis health: {'Healthy' if is_healthy else 'Unhealthy'}")
        
    except redis.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        print("\nTo start Redis:")
        print("  Windows: Download and run redis-server.exe")
        print("  Mac: brew services start redis")
        print("  Linux: sudo systemctl start redis")
