import asyncio
from typing import Optional
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError, RedisError

from backend.core.config import settings
from backend.core.logging import logger

_redis_client: Optional[aioredis.Redis] = None
_redis_client_loop: Optional[asyncio.AbstractEventLoop] = None


def get_redis_client() -> aioredis.Redis:
    """
    Returns or creates the shared asynchronous Redis client.

    Recreates the client if the running event loop has changed since it was
    created (e.g. across test-runner event loops), since the underlying
    connection pool's lock is bound to the loop that created it and cannot
    be reused across loops.
    """
    global _redis_client, _redis_client_loop

    try:
        current_loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is not None and current_loop is not None and _redis_client_loop is not current_loop:
        logger.warning("Event loop changed; discarding stale Redis client and recreating.")
        _redis_client = None
        _redis_client_loop = None

    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        _redis_client_loop = current_loop
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
    global _redis_client, _redis_client_loop
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception as e:
            logger.debug(f"Error closing Redis client: {e}")
        finally:
            _redis_client = None
            _redis_client_loop = None

