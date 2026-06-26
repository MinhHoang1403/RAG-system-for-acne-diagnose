"""
src/cache/redis_cache.py
========================
Redis client wrapper with fail-open logic.
"""
import os
import logging
from typing import Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: Optional['redis.Redis'] = None

async def get_redis() -> Optional['redis.Redis']:
    """
    Returns the async Redis client if available and enabled.
    """
    global _redis_client
    
    if not REDIS_AVAILABLE:
        return None
        
    cache_enabled = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    if not cache_enabled:
        return None
        
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            # Ping to verify connection
            await _redis_client.ping()
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}. Cache will be disabled.")
            _redis_client = None
            
    return _redis_client

async def close_redis():
    """Close the Redis connection if it exists."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception as e:
            logger.warning(f"Error closing Redis: {e}")
        _redis_client = None

async def ping_redis() -> bool:
    """Check if Redis is up."""
    client = await get_redis()
    if client is None:
        return False
    try:
        return await client.ping()
    except Exception:
        return False
