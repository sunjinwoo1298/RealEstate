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


async def enforce_customer_registration_rate_limit(identifier: str) -> None:
    """Rate-limits customer registration attempts (typically keyed by client IP). Fails open."""
    key = f"customer_register_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_REGISTRATION_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many registration attempts. Please try again later.")
    except RedisError as e:
        logger.warning(f"Customer registration rate limiter unavailable, failing open: {e}")


async def enforce_customer_login_rate_limit(identifier: str) -> None:
    """Rate-limits customer login attempts (typically keyed by client IP + normalized email). Fails open."""
    key = f"customer_login_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_LOGIN_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many login attempts. Please try again later.")
    except RedisError as e:
        logger.warning(f"Customer login rate limiter unavailable, failing open: {e}")


async def enforce_customer_verification_rate_limit(identifier: str) -> None:
    """Rate-limits email-verification/resend-verification requests (keyed by normalized email). Fails open."""
    key = f"customer_verify_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many verification requests. Please try again later.")
    except RedisError as e:
        logger.warning(f"Customer verification rate limiter unavailable, failing open: {e}")


async def enforce_customer_password_reset_rate_limit(identifier: str) -> None:
    """Rate-limits forgot-password/reset-password requests (keyed by normalized email). Fails open."""
    key = f"customer_pwreset_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many requests. Please try again later.")
    except RedisError as e:
        logger.warning(f"Customer password-reset rate limiter unavailable, failing open: {e}")


async def enforce_customer_conversation_rate_limit(identifier: str) -> None:
    """Rate-limits authenticated-customer conversation creation (keyed by customer_account_id). Fails open."""
    key = f"customer_conv_create_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_CONVERSATION_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_CONVERSATION_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many conversations started. Please try again later.")
    except RedisError as e:
        logger.warning(f"Customer conversation rate limiter unavailable, failing open: {e}")


async def enforce_customer_chat_message_rate_limit(identifier: str) -> None:
    """Rate-limits authenticated-customer chat messages (keyed by conversation id). Fails open."""
    key = f"customer_chat_msg_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_CHAT_MESSAGE_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_CHAT_MESSAGE_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many messages sent. Please slow down.")
    except RedisError as e:
        logger.warning(f"Customer chat message rate limiter unavailable, failing open: {e}")


async def enforce_customer_handoff_rate_limit(identifier: str) -> None:
    """Rate-limits authenticated-customer handoff requests (keyed by customer_account_id). Fails open."""
    key = f"customer_handoff_rl:{identifier}"
    client = get_redis_client()
    try:
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, settings.CUSTOMER_HANDOFF_RATE_LIMIT_WINDOW_SECONDS)
        if attempts > settings.CUSTOMER_HANDOFF_RATE_LIMIT_MAX_ATTEMPTS:
            raise RateLimitException(message="Too many requests for a sales executive. Please try again later.")
    except RedisError as e:
        logger.warning(f"Customer handoff rate limiter unavailable, failing open: {e}")
