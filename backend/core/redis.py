from typing import Optional
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError, RedisError

from backend.core.config import settings
from backend.core.logging import logger

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """
    Returns or creates the shared asynchronous Redis client.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_client


async def check_redis_connectivity() -> dict:
    """
    Checks whether Redis is reachable without raising unhandled exceptions.
    Returns status dict with connectivity information.
    """
    client = get_redis_client()
    try:
        ping_result = await client.ping()
        return {
            "status": "connected" if ping_result else "degraded",
            "message": "Redis ping successful",
            "url": settings.REDIS_URL.split("@")[-1],  # redact credentials if any
        }
    except (ConnectionError, RedisError, TimeoutError, OSError) as e:
        logger.debug(f"Redis connectivity check: {str(e)}")
        return {
            "status": "disconnected",
            "message": f"Redis unavailable: {type(e).__name__}",
            "url": settings.REDIS_URL.split("@")[-1],
        }


async def close_redis_connection() -> None:
    """
    Gracefully closes the Redis client connection.
    """
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception as e:
            logger.debug(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None

