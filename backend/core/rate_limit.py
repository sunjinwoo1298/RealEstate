from __future__ import annotations
from redis.exceptions import RedisError

from backend.core.config import settings
from backend.core.exceptions import RateLimitException
from backend.core.logging import logger
from backend.core.redis import get_redis_client


async def enforce_login_rate_limit(identifier: str) -> None:
    """
    Enforces a fixed-window rate limit on login attempts for the given identifier
    (typically a combination of client IP and normalized email).

    Fails open (logs and allows the request) if Redis is unreachable, since Redis
    is an optional dependency for this foundation and must never block authentication.
    """
    key = f"login_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(
                message="Too many login attempts. Please try again later.",
            )
    except RedisError as e:
        logger.warning(f"Login rate limiter unavailable, failing open: {e}")


async def enforce_chat_session_rate_limit(identifier: str) -> None:
    """
    Enforces a fixed-window rate limit on buyer chat session creation for the
    given identifier (typically client IP). Fails open if Redis is unreachable.
    """
    key = f"chat_session_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CHAT_SESSION_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CHAT_SESSION_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many session attempts. Please try again later.")
    except RedisError as e:
        logger.warning(f"Chat session rate limiter unavailable, failing open: {e}")


async def enforce_chat_message_rate_limit(identifier: str) -> None:
    """
    Enforces a fixed-window rate limit on buyer chat message submissions for
    the given identifier (typically a conversation id). Fails open if Redis
    is unreachable.
    """
    key = f"chat_message_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CHAT_MESSAGE_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many messages sent. Please slow down.")
    except RedisError as e:
        logger.warning(f"Chat message rate limiter unavailable, failing open: {e}")
